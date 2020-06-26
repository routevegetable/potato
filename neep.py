#!/usr/bin/env python3

import webcolors
import os
import http.client
import slack
import sys

# Slack integration!
my_id = None
@slack.RTMClient.run_on(event='message')
def say_hello(**payload):
    global my_id
    data = payload['data']

    #print(data)
    text = data.get('text', '')
    if not 'subtype' in data and ('<@' + my_id + '>' in text or data['channel'].startswith('D')):
        text_parts = text.split(' ')
        
        if len(text_parts) > 0:
            try:
                rgb = webcolors.html5_parse_legacy_color(text_parts[-1])
                print(str(rgb))
                #print(str(payload['timestamp']))
            
                conn = http.client.HTTPConnection("127.0.0.1:8080")
                conn.request("GET","/vars/col?set=" + str(int(webcolors.rgb_to_hex((rgb.blue, rgb.green, rgb.red))[1:],16)))
                r1 = conn.getresponse()
                conn.close()
            
                #payload['web_client'].chat_postMessage(
                #    channel=data['channel'],
                #    text="Set color to: " + webcolors.rgb_to_hex((rgb.red, rgb.green, rgb.blue)),
                #    thread_ts=data['ts']
                #)
                payload['web_client'].reactions_add(
                    channel=data['channel'],
                    name='thumbsup',
                    timestamp=data['ts']
                )
            except:
                print("Error: " + str(sys.exc_info()[0]))

            
slack_token = os.environ["SLACK_API_TOKEN"]
web_client = slack.WebClient(token=slack_token)
my_id = [user['id'] for user in web_client.users_list()['members'] if user['name'] == 'neep'][0]
print(my_id)
rtm_client = slack.RTMClient(token=slack_token)
rtm_client.start()
