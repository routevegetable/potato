#!/usr/bin/env python3

import webcolors
import os
import http.client
import slack

# Slack integration!
my_id = None
@slack.RTMClient.run_on(event='message')
def say_hello(**payload):
    global my_id
    data = payload['data']
    
    text = data.get('text', '')
    if '<@' + my_id + '>' in text or data['channel'].startswith('D'):
        text_parts = text.split(' ')
        
        if len(text_parts) > 0:
            rgb = webcolors.html5_parse_legacy_color(text_parts[-1])
            print(str(rgb))
            
            conn = http.client.HTTPConnection("localhost:8080")
            conn.request("GET","/vars/col?set=" + str(int(webcolors.rgb_to_hex((rgb.blue, rgb.green, rgb.red))[1:],16)))
            r1 = conn.getresponse()
            conn.close()

            
slack_token = os.environ["SLACK_API_TOKEN"]
web_client = slack.WebClient(token=slack_token)
my_id = [user['id'] for user in web_client.users_list()['members'] if user['name'] == 'neep'][0]
print(my_id)
rtm_client = slack.RTMClient(token=slack_token)
rtm_client.start()
