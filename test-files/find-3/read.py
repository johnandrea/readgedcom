import sys
import readgedcom
import pprint

options = { 'display-gedcom-warnings': False, 'show-settings': False }

data = readgedcom.read_file( sys.argv[1], options )

print( 'object details for everyone' )
for indi in data[readgedcom.PARSED_INDI]:
    print( '' )
    pprint.pprint( data[readgedcom.PARSED_INDI][indi] )


def expected( title, got, wanted ):
    print( '' )
    print( title )
    readgedcom.print_individuals( data, got )
    print( 'should have shown id', wanted )

# assuming that the gedcom is defined properly with givn and surn name records

expected( 'find Smiths', readgedcom.find_individuals( data, 'name.surn', 'Smith', '=' ), '1 and 2' )

expected( 'not Smiths', readgedcom.find_individuals( data, 'name.surn', 'Smith', 'not' ), '3, 4 and 5' )

expected( 'smith anywhere', readgedcom.find_individuals( data, 'name', 'Smith', 'in' ), '1, 2 and 5' )

# use "in" for givn because of possible existance of middle name

expected( 'find Eileen', readgedcom.find_individuals( data, 'name.givn', 'Eileen', 'in' ), '1 and 4' )

expected( 'not Eileen', readgedcom.find_individuals( data, 'name.givn', 'Eileen', 'not in' ), '2, 3 and 5' )
