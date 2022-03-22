import json
import pprint


def slew_action(sline, sat_id):
    """
    Template:
    "sat_id" : 2,
    "type" : "slew",
    "start" : 0,
    "end" : 1,
    "info" : {
      "starting_angle" : 35,
      "target_angle" : 34
    }
    """
    type = "slew"

    start = ''
    end = ''
    break_found = False
    for c in sline[0]:
        if c is '[' or c is ']':
            continue
        elif c is '-':
            break_found = True
            continue

        if not break_found:
            start += c
        else:
            end += c
    return ''

def measurement_action(sline):
    """
    Template:
    "sat_id": 2,
    "type": "measurement",
    "start": 0,
    "end": 1,
    "info": {
        "instrument": "L",
        "angle": 34,
        "targets": [195112, 195113, 195114, 195115, 195116]
        "energy"
    """

    sat_id = sline[0][1:]
    type = 'measurement'

    start = ''
    end = ''
    break_found = False
    for c in sline[1]:
        if c is '[' or c is ']':
            continue
        elif c is '-':
            break_found = True
            continue

        if not break_found:
            start += c
        else:
            end += c
    instrument, angle = sline[2].split('.')

    targets = sline[3]
    i = 4
    while sline[i] != 'energy':
        targets += sline[i]
        i += 1
    targets = targets[1:(len(targets)-2)].split(',')

    energy = sline[i+1]

    info = {}
    info['instrument'] = instrument
    info['angle'] = angle
    info['targets'] = targets
    info['energy'] = energy

    action = {}
    action['sat_id'] = sat_id
    action['type'] = type
    action['start'] = start
    action['end'] = end
    action['info'] = info

    # action_json = json.dumps(action)
    return action

def parse_plan(filename):
    with open(filename, 'r') as file:
        # file_contents = file.read()
        actions = []
        sat_id = ''
        for line in file.readlines():
            sline = line.split()

            if line is '\n':
                continue

            print(line)

            action_json = None
            if sline[0][0] is '[' and len(sline) > 3 and sline[3] == 'slew:':
                # action_json = slew_action(sline, sat_id)
                continue
            elif sline[0][0] is 's' and sline[0][1].isnumeric() and sline[1][0] is '[':
                action_json = measurement_action(sline)
            elif sline[0][0] is 's' and sline[0][1].isnumeric():
                sat_id = sline[0][1:]

            if action_json is not None:
                actions.append(action_json)

        output = json.dumps(actions)

        pretty_print_json = pprint.pformat(actions).replace("'", '"')

        name = filename[0:(len(filename)-4)]
        with open('./plans' +name + '.json', 'w') as f:
            f.write(pretty_print_json)


parse_plan('s2.1-21600.combinedPlan.txt')
