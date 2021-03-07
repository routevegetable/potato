
import json
import os
import subprocess

class PotatoApp:
    def __init__(self):
        self.prog_vars = {}
        self.sync_vars = []
        self.APP_FILE = 'app.c'
        self.VAR_FILE = 'vars.json'
        self.app_process = None

    def make_var_block(self, obj):
        s = ''
        for name in obj:
            s += name + '\n'
            s += json.dumps(obj[name]) + '\n'
        s += '\n'
        return s

    def send_var_block(self, obj):
        blk = self.make_var_block(obj)
        print(blk)
        self.app_process.stdin.write(bytes(blk, 'UTF-8'))
        self.app_process.stdin.flush()

    def save_vars(self):
        with open(self.VAR_FILE, 'w') as f:
            print('saving {}'.format(self.prog_vars))
            json.dump(self.prog_vars, f, indent=4, separators=(',', ': '))

    def load_vars(self):
        if os.path.exists(self.VAR_FILE):
            with open(self.VAR_FILE, 'r') as f:
                self.prog_vars = json.load(f)
        else:
            self.prog_vars = {}

    def update_var(self, name, value):
        print('update var {} = {}'.format(name,value))
        self.prog_vars[name] = value
        if name in self.sync_vars:
            self.send_var_block({name:self.prog_vars[name]})

    def is_sync_var(self, name):
        return name in self.sync_vars

    def get_vars(self):
        return self.prog_vars.copy()

    def remove_var(self, name):
        del self.prog_vars[name]

    def get_var_value(self, name):
        if name in self.prog_vars:
            return self.prog_vars[name]
        else:
            return None

    def reload_app(self):

        with open(self.APP_FILE, 'w') as f:
            f.write(self.prog_vars['code'])

        # Rebuild
        completed = subprocess.run(['make'],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)

        if completed.returncode == 0:
            # Kill the running process
            if self.app_process:
                self.app_process.kill()
                self.app_process.wait()


            # Find the vars we are interested in syncing

            # Always sync fps
            self.sync_vars = ['fps']
            with open(self.APP_FILE, 'r') as f:
                for line in f.readlines():
                    line = line.strip()
                    if line.startswith('DEFVAR('):
                        line = line[7:].split(')')[0]
                        parts = line.split(',')
                        var_type = parts[0].strip()
                        var_name = parts[1].strip()
                        self.sync_vars.append(var_name)

            print('sync vars: ' + str(self.sync_vars))

            os.system('sudo setcap cap_sys_rawio+ep ./app')

            # Redeploy
            self.app_process = subprocess.Popen(['./app'],
                                                stdin=subprocess.PIPE)

            # Start the app with the set of current vars
            self.send_var_block({k:v for (k,v) in self.prog_vars.items() if k in self.sync_vars})

        return completed
