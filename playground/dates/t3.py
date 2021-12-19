import sys
import dateparser
import arrow

def fill( n, s ):
    return s + ' ' * max( 0, n-len(s) )

def run_test( s ):
    out = fill( 15, s )

    out += ' | '
    try:
       x = dateparser.parse( s )
       out += fill( 10, str( x.date() ) )
    except:
       #e = sys.exc_info()[0]
       e = 'err'
       out += fill( 10, str(e) )

    out += ' | '
    try:
       x = arrow.get( s )
       out += fill( 10, str( x.date() ) )
    except:
       #e = sys.exc_info()[0]
       e = 'err'
       out += fill( 10, str(e) )

    print( out )


out = fill( 15, 'date' )
out += ' | '
out += fill( 10, 'dateparser' )
out += ' | '
out += fill( 10, 'arrow' )
print( out )


run_test( '10 mar 1982' )
run_test( '1982 mar 10' )
run_test( '1970 jan 1' )
run_test( '1969 dec 31' )
run_test( '3 oct 1860' )
run_test( '3-oct-1860' )
run_test( '1860-oct-3' )
run_test( '1860-10-3' )
run_test( '3-10-1860' )
run_test( 'wrong-1907' )
run_test( '1907-wrong' )
run_test( '1907 wrong' )
run_test( 'wrong 1907' )
