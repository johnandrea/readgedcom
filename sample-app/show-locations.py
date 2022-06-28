import sys
import readgedcom

# display the date and locations for everyone's events

def show_1_record( indi, name, event_name, event_data ):
    if 'date' in event_data and 'plac' in event_data:
       if event_data['date']['is_known']:
          # or to fisplay the date exactly as in ged, not parsed
          # date = event_data['in']
          # but this one will be sortable "yyyymmdd abt/bef/aft"
          date = event_data['date']['min']['value'] + ' ' + event_data['date']['min']['modifier'].upper()
          print( indi, name, event_name, event_data['plac'], date.strip() )


def show_records( indi, name, event_list, data_record ):
    other_type = 'even'

    for event_type in event_list:
        if event_type == other_type:
           continue
        if event_type in data_record:
           if event_type in data_record[readgedcom.BEST_EVENT_KEY]:
              best = data_record[readgedcom.BEST_EVENT_KEY][event_type]
              show_1_record( indi, name, event_type, data_record[event_type][best] )
           else:
              # not a single event type, instead event such as census over multiple years
              # show all of them
              for event_record in data_record[event_type]:
                  show_1_record( indi, name, event_type, event_record )

    # "even" tagged records do not have "best" selection
    if other_type in event_list:
       if other_type in data_record:
          for event_data in data_record[other_type]:
              show_1_record( indi, name, event_data['type'], event_data )


def all_records( indi, name ):
    # standard individual events
    show_records( indi, name, readgedcom.INDI_EVENT_TAGS, data[i_key][indi] )

    # and family events
    if 'fams' in data[i_key][indi]:
       for fam in data[i_key][indi]['fams']:
           show_records( indi, name, readgedcom.FAM_EVENT_TAGS, data[f_key][fam] )

opts = dict()
opts['display-gedcom-warnings'] = False

data = readgedcom.read_file( sys.argv[1], opts )

i_key = readgedcom.PARSED_INDI
f_key = readgedcom.PARSED_FAM

for indi in data[i_key]:
    all_records( indi, data[i_key][indi]['name'][0]['display'] )
