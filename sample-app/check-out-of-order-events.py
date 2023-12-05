import sys
import readgedcom

# Parameters:
# 1 = GEDCOM file to test
# Output:
# messages on stdout
#
# Check for events that occur before birth or after burial.
# If there is no burial date, try to use death date.
# Event dates equal to birth or burial/death are ok.
#
# Not checking for family events out of order (marriage before birth, etc.)

month_days = [ 0, #make indexes start at 1
              31, 28, 31, 30,
              31, 30, 31, 31,
              30, 31, 30, 31]

def is_leap_year( y ):
    result = False
    if y % 4 == 0:
       result = True
       if y % 100 == 0:
          result = False
          if y % 400 == 0:
             result = True
    return result

def ymd_as_yyyymmdd( y, m, d ):
    # integers into a single string and zero pad too
    m = str( m )
    if len( m ) == 1:
       m = '0' + m
    d = str( d )
    if len( d ) == 1:
       d = '0' + d
    return str( y ) + m + d

# I'm not afraid of doing these simple date calculations.
# Besides, these are usable before the Unix epoch which
# many date libraries can't handle.
# I don't expect to worry about the Gregorian switchover.
# But they do assume handled dates are valid.

def subtract_one_day( s ):
    # input and output is string yyyymmdd
    year = int( s[0:4] )
    month = int( s[4:6] )
    day = int( s[6:8] )

    day -= 1
    if day < 1:
       month -= 1
       if month < 1:
          # jump to prev year
          day = month_days[12]
          month = 12
          year -= 1
       else:
          # same year
          month_end = month_days[month]
          if month == 2 and is_leap_year( year ):
             month_end += 1
          day = month_end

    return ymd_as_yyyymmdd( year, month, day )

def add_one_day( s ):
    # input and output is string yyyymmdd
    year = int( s[0:4] )
    month = int( s[4:6] )
    day = int( s[6:8] )

    month_end = month_days[month]
    if month == 2 and is_leap_year( year ):
       month_end += 1

    day += 1
    if day > month_end:
       day = 1
       month += 1
       if month > 12:
          month = 1
          year += 1

    return ymd_as_yyyymmdd( year, month, day )

def comparable_date( event_date ):
    # date values already are comparable as strings of "yyyymmdd"
    # but the modifiers need to be considered

    result = event_date['value']

    if event_date['modifier'].lower() == 'bef':
       result = subtract_one_day( result )
    elif event_date['modifier'].lower() == 'aft':
       result = add_one_day( result )

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
