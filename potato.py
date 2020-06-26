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
        json.dump(prog_vars, f, indent=4, separators=(',', ': '))

def load_vars():
    global prog_vars
    if os.path.exists(VAR_FILE):
        with open(VAR_FILE, 'r') as f:
            prog_vars = json.load(f)
    else:
        prog_vars = {}


def mqtt_on_connect(client, userdata, flags, rc):
    print('connected with result code {}'.format(rc))

    client.subscribe(TOPIC_PREFIX + '/#')

def mqtt_on_message(client, userdata, msg):

    global sync_vars
    global prog_vars

    topic_parts = msg.topic.split('/')

    if topic_parts[1] == 'vars':
        var_name = topic_parts[2]

        value = msg.payload.decode('utf-8')

        prog_vars[var_name] = json.loads(value)

        if var_name in sync_vars:
            send_var_block({var_name: prog_vars[var_name]})

    print(msg.topic)
    print('payload: {}'.format(msg.payload))

client = mqtt.Client()
client.on_connect = mqtt_on_connect
client.on_message = mqtt_on_message

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

client.connect(BROKER_HOST)

httpfd = httpd.fileno()

while True:
    mqttsock = client.socket()

    r,w,e = select(
        [mqttsock, httpfd],
        [mqttsock] if client.want_write() else [],
        [],
        1)

    if mqttsock in r:
        client.loop_read()

    if mqttsock in w:
        client.loop_write()

    client.loop_misc()

    if httpfd in r:
        httpd.handle_request()
