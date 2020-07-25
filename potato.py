#!/usr/bin/env python3

import http.server
import shutil
import json
import urllib
import subprocess
import os
import os.path
import mimetypes
import paho.mqtt.client as mqtt
import aioblescan as ble
import asyncio
import os

from select import select

PORT = 8080

# Dict of var(with type) -> value string
prog_vars = {}

# List of vars we want to sync
# gleaned from parsing app.c
sync_vars = []

# C file that app lives in
APP_FILE='app.c'

# Persistent state lives here
VAR_FILE='vars.json'

# Handle for the running app, if it is indeed running
app_process = None

# MQTT broker is here
BROKER_HOST="127.0.0.1"

TOPIC_PREFIX="neep"


def make_var_block(obj):
    s = ''
    for name in obj:
        s += name + '\n'
        s += json.dumps(obj[name]) + '\n'
    s += '\n'
    return s

def send_var_block(obj):
    global app_process
    blk = make_var_block(obj)
    print(blk)
    app_process.stdin.write(bytes(blk, 'UTF-8'))
    app_process.stdin.flush()

def save_vars():
    global prog_vars
    with open(VAR_FILE, 'w') as f:
        print('saving {}'.format(prog_vars))
        json.dump(prog_vars, f, indent=4, separators=(',', ': '))

def load_vars():
    global prog_vars
    if os.path.exists(VAR_FILE):
        with open(VAR_FILE, 'r') as f:
            prog_vars = json.load(f)
    else:
        prog_vars = {}


def mqtt_on_connect(mc, userdata, flags, rc):
    print('connected with result code {}'.format(rc))

    mc.subscribe(TOPIC_PREFIX + '/#')

def mqtt_on_message(mc, userdata, msg):

    global sync_vars
    global prog_vars

    topic_parts = msg.topic.split('/')
    if msg.retain:
        print('dropping retained message for {}'.format(msg.topic))
        return


    if topic_parts[1] == 'vars':
        var_name = topic_parts[2]

        value = msg.payload.decode('utf-8')

        prog_vars[var_name] = json.loads(value)

        if var_name in sync_vars:
            send_var_block({var_name: prog_vars[var_name]})

    print(msg.topic)
    print('payload: {}'.format(msg.payload))

mc = mqtt.Client()
mc.on_connect = mqtt_on_connect
mc.on_message = mqtt_on_message

class RequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global prog_vars
        global sync_vars

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
            self.reply(prog_vars)


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
                prog_vars[var_name] = json.loads(value)

                if var_name in sync_vars:
                    global mc
                    mc.publish(TOPIC_PREFIX + '/vars/' + var_name, json.dumps(prog_vars[var_name]))
                    send_var_block({var_name: prog_vars[var_name]})

                self.reply(prog_vars[var_name])
            elif delete:
                del prog_vars[var_name]
                self.reply(None)
            else:
                if var_name in prog_vars:
                    self.reply(prog_vars[var_name])
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
        global prog_vars
        global sync_vars


        if self.path.startswith('/vars/'):

            # Setting a var
            parts = self.path.split('?')
            var_name = parts[0].split('/')[2]

            value = str(self.rfile.read(int(self.headers['Content-length'])), 'UTF-8')

            prog_vars[var_name] = json.loads(value)


            # No point in sending the code to the process.
            # That would be awfully silly...
            if var_name in sync_vars:
                send_var_block({var_name: prog_vars[var_name]})

            self.reply(prog_vars[var_name])

    def reply(self, obj):
        self.send_response(200)
        self.send_header('Content-type', 'application/json');
        self.end_headers()

        j = json.dumps(obj)
        self.wfile.write(bytes(j, 'UTF-8'))


httpd = http.server.HTTPServer(('', PORT), RequestHandler)


def reload_app():
    global sync_vars
    global prog_vars

    with open(APP_FILE, 'w') as f:
        f.write(prog_vars['code'])

    # Rebuild
    completed = subprocess.run(['make'],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)

    if completed.returncode == 0:
        # Kill the running process
        global app_process
        if app_process:
            app_process.kill()
            app_process.wait()


        # Find the vars we are interested in syncing

        # Always sync fps
        sync_vars = ['fps']
        with open(APP_FILE, 'r') as f:
            for line in f.readlines():
                line = line.strip()
                if line.startswith('DEFVAR('):
                    line = line[7:].split(')')[0]
                    parts = line.split(',')
                    var_type = parts[0].strip()
                    var_name = parts[1].strip()
                    sync_vars.append(var_name)

        print('sync vars: ' + str(sync_vars))


        # Redeploy
        app_process = subprocess.Popen(['./app'],
                                       stdin=subprocess.PIPE)

        # Start the app with the set of current vars
        send_var_block({k:v for (k,v) in prog_vars.items() if k in sync_vars})

    return completed



load_vars()

reload_app()

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

    print('mfg_id {:02X}, payload: {}'.format(mfg_id, msd_payload))

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
        if not k in prog_vars or not prog_vars[k] == v:
            prog_vars[k] = v
            print('BLE {} = {}'.format(k,v))
            mc.publish(TOPIC_PREFIX + '/vars/' + k, json.dumps(prog_vars[k]))
            send_var_block({k: prog_vars[k]})


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
