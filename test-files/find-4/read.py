import sys
import pprint
import collections
import readgedcom

options = { 'display-gedcom-warnings': False, 'show-settings': False }

data = readgedcom.read_file( sys.argv[1], options )

print( 'individual details' )
print( '' )
pprint.pprint( data[readgedcom.PARSED_INDI]['i1'] )
print( '' )
pprint.pprint( data[readgedcom.PARSED_INDI]['i2'] )
print( '' )
pprint.pprint( data[readgedcom.PARSED_INDI]['i3'] )


def expected( title, got, wanted ):
    print( '' )
    print( title )
    readgedcom.print_individuals( data, got )
    print( 'expected', wanted )
    test_wanted = ['i' + str(i) for i in wanted]
    if collections.Counter( got ) != collections.Counter( test_wanted ):
       print( 'WRONG answer', got, test_wanted )


expected( 'has birth', readgedcom.find_individuals( data, 'birth', '', 'exist'), [1, 2, 3] )

expected( 'has birth date', readgedcom.find_individuals( data, 'birt.date', '', 'exist'), [1,3] )

expected( 'has birth place', readgedcom.find_individuals( data, 'birt.place', '', 'exist'), [1,2] )
