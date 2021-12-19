#!/usr/bin/python3

import datetime
import arrow

# datetime fails on MS-Windows 7 -native library can't handle unix epoch and before

def fill( n, s ):
    return s + ' ' * max( 0, n-len(s) )

def run_test( y, m, d ):
    out = fill( 10, str(y) + '-' + str(m) + '-' + str(d) )
    out += ' | '
    try:
       x = datetime.datetime( y, m, d )
       out += fill( 14, str( x.timestamp() ) )
    except:
       out += fill( 14, 'err' )
    out += ' | '
    try:
       x = arrow.get( y, m, d )
       out += fill( 14, str( x.float_timestamp ) )
    except:
       out += fill( 14, 'err' ) 
    print( out )

out = fill( 10, 'yyy-mm-dd' )
out += ' | '
out += fill( 14, 'datetime' )
out += ' | '
out += fill( 14, 'arrow' )
print( out )

run_test( 2020, 7, 9 )
run_test( 1970, 1, 2 )
run_test( 1970, 1, 1 )
run_test( 1969, 12, 31 )
run_test( 1960, 11, 30 )
run_test( 1909, 1, 2 )
run_test( 1808, 3, 4 )
run_test( 1707, 5, 6 )
run_test( 1606, 8, 9 )