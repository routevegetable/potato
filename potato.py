#!/usr/bin/env python3

import http.server
import shutil
import json
import urllib
import os
import os.path
import mimetypes
import paho.mqtt.client as mqtt
import aioblescan as ble
import asyncio
import os
import potato_app


from select import select

PORT = 8080

# MQTT broker is here
BROKER_HOST="127.0.0.1"

TOPIC_PREFIX="neep"

app = potato_app.PotatoApp()


def mqtt_on_connect(mc, userdata, flags, rc):
    print('connected with result code {}'.format(rc))

    mc.subscribe(TOPIC_PREFIX + '/#')

def mqtt_on_message(mc, userdata, msg):

    print('mqtt {}'.format(msg.topic))

    topic_parts = msg.topic.split('/')
    if msg.retain:
        print('dropping retained message for {}'.format(msg.topic))
        return

    if topic_parts[1] == 'vars':
        var_name = topic_parts[2]

        value = msg.payload.decode('utf-8')
        value = json.loads(value)

        app.update_var(var_name,value)

mc = mqtt.Client()
mc.on_connect = mqtt_on_connect
mc.on_message = mqtt_on_message

class RequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):

        if self.path == '/':
            self.send_response(302)
            self.send_header('Location', '/static/index.html')
            self.end_headers()
        elif self.path.startswith('/static/'):
            path = self.path.split('/')[2]

            if os.path.exists(path):
                mime = mimetypes.guess_type(path)

                with open('./'+ path, 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', mime[0])
                    self.end_headers()
                    shutil.copyfileobj(f, self.wfile,length=16*1024*1024)
            else:
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()

        elif self.path == '/vars':
            self.reply(app.get_vars())


        elif self.path.startswith('/vars/'):
            # Getting/Setting a var
            parts = self.path.split('?')
            var_name = parts[0].split('/')[2]

            value = None
            delete = False
            if len(parts) > 1:
                query_string = parts[1]
                qs = urllib.parse.parse_qs(query_string)
                if 'set' in qs:
                    value = qs['set'][0]
                elif 'delete' in qs:
                    delete = True

            if value:
                app.update_var(var_name, json.loads(value))

                if app.is_sync_var(var_name):
                    mc.publish(TOPIC_PREFIX + '/vars/' + var_name, value)

                self.reply(app.get_var_value(var_name))
            elif delete:
                app.remove_var(var_name)
                self.reply(None)
            else:
                all_vars = app.get_vars()
                if var_name in all_vars:
                    self.reply(all_vars[var_name])
                else:
                    self.reply(None)

        elif self.path == '/save':
            save_vars()
            self.reply(None)

        elif self.path == '/reload':

            completed = reload_app()
            self.reply({'returncode': completed.returncode,
                        'stdout': str(completed.stdout, 'UTF-8'),
                        'stderr': str(completed.stderr, 'UTF-8')
            })

        else:
            self.reply('hello from ' + self.path)

    def do_POST(self):

        if self.path.startswith('/vars/'):

            # Setting a var
            parts = self.path.split('?')
            var_name = parts[0].split('/')[2]

            value = str(self.rfile.read(int(self.headers['Content-length'])), 'UTF-8')

            value = json.loads(value)
            app.update_var(var_name, value)

            self.reply(value)

    def reply(self, obj):
        self.send_response(200)
        self.send_header('Content-type', 'application/json');
        self.end_headers()

        j = json.dumps(obj)
        self.wfile.write(bytes(j, 'UTF-8'))


httpd = http.server.HTTPServer(('', PORT), RequestHandler)


app.load_vars()

app.reload_app()

# Todo: propagate sync_vars back to here
# Use an 'order token' var to ensure all sent messages have been
# processed.
# This should be a long defined in potato.c
# Use in-band messaging on stdout
# Use select here to poll the network socket and the app process.
# Collect log data in a circular buffer.
# Allow clients to pull from the buffer, given a starting index.
# In-band data starts with a ===VAR_BLOCK=== line
# The app will send all of its 'sync vars' in here.

httpfd = httpd.fileno()

# Make handle_request nonblocking
httpd.timeout = 0

mc.connect(BROKER_HOST)



# Bluetooth stuff now!

rpipe,wpipe = os.pipe()

wpipe = os.fdopen(wpipe, 'w')
rpipe = os.fdopen(rpipe)

def handle_ble_packet(data):
    ev = ble.HCI_Event()
    xx = ev.decode(data)
    msds = ev.retrieve("Manufacturer Specific Data")
    if(len(msds) > 0):
        msd = msds[0]
    else:
        return

    mfg_id = msd.payload[0].val
    msd_payload = msd.payload[1].val

    if mfg_id != 0x9001:
        return

    import struct
    value = struct.unpack('i', msd_payload[2:6])[0]

    rest = msd_payload[6:]
    name = rest[:rest.index(0)].decode('utf-8')

    msg = json.dumps({name: value})
    print('BLE {}'.format(msg))
    wpipe.write(msg + '\n')
    wpipe.flush()






loop = asyncio.get_event_loop()
btsock = ble.create_bt_socket()
fac=loop._create_connection_transport(btsock,ble.BLEScanRequester,None,None)

btconn,btctl = loop.run_until_complete(fac)

btctl.process = handle_ble_packet

mqttsock = None
def ensure_mqtt():
    # Reconnect crap
    global mqttsock
    if mqttsock:
        if wr_en:
            loop.remove_writer(mqttsock)
            loop.remove_reader(mqttsock)
    mqttsock = mc.socket()
    while not mqttsock:
        print('Reconnecting...')
        mc.connect(BROKER_HOST)
        mqttsock = mc.socket()
        loop.remove_reader(mqttsock)
    loop.add_reader(mqttsock, ev_mqtt_read)
    check_mqtt_write()

def ev_periodic():
    print('mqtt periodic')
    ensure_mqtt()
    mc.loop_misc()
    check_mqtt_write()
    loop.call_later(1, lambda: ev_periodic())

def ev_mqtt_read():
    print('mqtt read')
    ensure_mqtt()
    mc.loop_read()
    check_mqtt_write()

def ev_mqtt_write():
    print('mqtt write')
    ensure_mqtt()
    mc.loop_write()
    check_mqtt_write()

def ev_ble_read():
    msg = rpipe.readline().strip()
    obj = json.loads(msg)

    print('ble read {}'.format(obj))
    for k in obj:
        v = obj[k]

        current = app.get_var_value(k)
        if not current or current != v:
            app.update_var(k,v)
            mc.publish(TOPIC_PREFIX + '/vars/' + k, json.dumps(v))

wr_en = False
def check_mqtt_write():
    global wr_en
    if mc.want_write():
        if not wr_en:
            loop.add_writer(mqttsock, ev_mqtt_write)
            wr_en = True
    else:
        if wr_en:
            loop.remove_writer(mqttsock)
            wr_en = False


loop.add_reader(httpfd, lambda: httpd.handle_request())

loop.add_reader(rpipe, lambda: ev_ble_read())

loop.call_soon(ev_periodic)

ensure_mqtt()

btctl.send_scan_request()

loop.run_forever()
