import sys
import readgedcom

# Check for events that occur before birth or after burial.
# If there is no burial date, try to use death date.
# Dates equal to birth or burial are ok.
# Not checking for family events out of order (marriage before birth, etc.)


def comparable_date( event_date ):
    # date values already are comparable as strings of "yyyymmdd"
    # but the modifiers need to be considered to be correct

    result = event_date['value']

    if event_date['modifier'].lower() == 'bef':
       # naive
       result = str( int(result) - 1 )
    if event_date['modifier'].lower() == 'aft':
       # naive
       result = str( int(result) + 1 )

    return result


def get_best_event_date( data, event_type, range_end ):
    result = None

    if event_type in data:
       best = 0
       if event_type in data[readgedcom.BEST_EVENT_KEY]:
          best = data[readgedcom.BEST_EVENT_KEY][event_type]
       if 'date' in data[event_type][best]:
          if data[event_type][best]['date']['is_known']:
             result = comparable_date( data[event_type][best]['date'][range_end] )
    return result


def check_person( person ):
    # compare events to the two possible end points

    def print_match( name, message, do_new_line ):
        if do_new_line:
           print( '' )
        print( name, message )
        return False

    def check_event( name, event, event_type, new_line ):
        if 'date' in event and event['date']['is_known']:
           event_date = comparable_date( event['date']['min'] )

           if first_date and (event_type != first_event):
              if event_date < first_date:
                 new_line = print_match( name, event_type+' before '+first_event, new_line )
           if last_date and (event_type != last_event):
              if event_date > last_date:
                 new_line = print_match( name, event_type+' after '+last_event, new_line )
        return new_line

    first_event = 'birt'
    first_date = get_best_event_date( person, first_event, 'min' )
    # possibly use baptism if no birth, but they usually go together
    last_event = 'buri'
    last_date = get_best_event_date( person, last_event, 'max' )
    if not last_date:
       # try death
       last_event = 'deat'
       last_date = get_best_event_date( person, last_event, 'max' )

    if first_date or last_date:
       separator = True #a newline the first time a person is output
       name = 'xref:' + str( person['xref'] ) + ' ' + person['name'][0]['display']

       if 'even' in person:
          for event in person['even']:
              separator = check_event( name, event, event['type'], separator )

       # now the regular events
       for event_type in readgedcom.INDI_EVENT_TAGS:
           if event_type in person and (event_type != 'even'):
              for event in person[event_type]:
                  separator = check_event( name, event, event_type, separator )


opts = dict()
opts['display-gedcom-warnings'] = False
# only deal with dates that are useful
opts['exit-on-bad-date'] = True

data = readgedcom.read_file( sys.argv[1], opts )

i_key = readgedcom.PARSED_INDI

for indi in data[i_key]:
    check_person( data[i_key][indi] )
