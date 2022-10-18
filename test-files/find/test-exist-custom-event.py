import sys
import collections
import readgedcom

data = readgedcom.read_file( 'test-exist-custom-event.ged' )


def expected( title, got, wanted ):
    print( '' )
    print( title )
    readgedcom.print_individuals( data, got )
    print( 'expected', wanted )
    test_wanted = ['i' + str(i) for i in wanted]
    if collections.Counter( got ) != collections.Counter( test_wanted ):
       print( 'WRONG answer', got, test_wanted )


print( 'everyone with a name' )
everyone = readgedcom.find_individuals( data, 'name', '', 'exist' )
readgedcom.print_individuals( data, everyone )

expected( 'has blood fact', readgedcom.find_individuals( data, 'even.blood', '', 'exist' ), [1,2] )
