import sys
import collections
import pprint
import readgedcom

options = { 'display-gedcom-warnings': False, 'show-settings': False }

data = readgedcom.read_file( sys.argv[1], options )

print( 'object details for a few individuals' )
print( '' )
pprint.pprint( data[readgedcom.PARSED_INDI]['i5'] )
print( '' )
pprint.pprint( data[readgedcom.PARSED_INDI]['i8'] )
print( '' )
pprint.pprint( data[readgedcom.PARSED_INDI]['i13'] )

def expected( title, got, wanted ):
    print( '' )
    print( title )
    readgedcom.print_individuals( data, got )
    print( 'expected', wanted )
    test_wanted = ['i' + str(i) for i in wanted]
    if collections.Counter( got ) != collections.Counter( test_wanted ):
       print( 'WRONG answer', got, test_wanted )


expected( 'find xref 13', readgedcom.find_individuals( data, 'xref', '@i13@' ), [13] )

select1 = readgedcom.find_individuals( data, 'xref', 12, '>' )
select2 = readgedcom.find_individuals( data, 'xref', 14, '<' )
expected( 'find xref 13', readgedcom.list_intersection( select1, select2 ), [13] )

expected( 'with dna', readgedcom.find_individuals( data, 'even.dna', '', 'exist' ), [5, 16] )

expected( 'has dna 42', readgedcom.find_individuals( data, 'even.dna', '42', '=' ), [16] )

expected( 'has dna 60', readgedcom.find_individuals( data, 'even.dna', '60', '=' ), [5, 16] )

expected( 'every male', readgedcom.find_individuals( data, 'sex', 'M', '=' ), [2, 3] )

expected( 'every female', readgedcom.find_individuals( data, 'sex', 'F', '=' ), [4, 14] )

expected( 'every make; only-best=false', readgedcom.find_individuals( data, 'sex', 'M', '=', False ), [2, 3, 14] )

expected( 'every femake; only-best=false', readgedcom.find_individuals( data, 'sex', 'F', '=', False ), [2, 4, 14] )

expected( 'refn 456', readgedcom.find_individuals( data, 'refn', '456', '=' ), [13] )

expected( 'refn 789', readgedcom.find_individuals( data, 'refn', '789', '=' ), [13] )

expected( 'name contains alt', readgedcom.find_individuals( data, 'name', 'Alt', 'in', True ), [] )

expected( 'name contains alt; only-best=false', readgedcom.find_individuals( data, 'name', 'Alt', 'in', False ), [1, 15] )

expected( 'has birth', readgedcom.find_individuals( data, 'birth', '', 'exist'), [5,6,7,8,9,10,11] )

expected( 'has death', readgedcom.find_individuals( data, 'death', '', 'exist'), [] )
expected( 'has death date', readgedcom.find_individuals( data, 'deat.date', '', 'exist'), [] )
expected( 'has death place', readgedcom.find_individuals( data, 'death.place', '', 'exist'), [] )

expected( 'has birth date', readgedcom.find_individuals( data, 'birt.date', '', 'exist'), [5,6,7, 11] )

expected( 'has birth place', readgedcom.find_individuals( data, 'birt.place', '', 'exist'), [8,9,10] )

select1 = readgedcom.find_individuals( data, 'birth.date', '19391231', '>')
select2 = readgedcom.find_individuals( data, 'birth.date', '19410101', '<')
expected( 'born in 1940', readgedcom.list_intersection( select1, select2 ), [6] )

expected( 'born after 1949', readgedcom.find_individuals( data, 'birth.date', '19491231', '>'), [7] )

expected( 'born after 1949; only-best=false', readgedcom.find_individuals( data, 'birth.date', '19491231', '>', False), [7, 11] )

expected( 'born in Toronto', readgedcom.find_individuals( data, 'birt.place', 'To', 'in'), [8, 10] )

expected( 'born in Montreal', readgedcom.find_individuals( data, 'birt.place', 'Montreal', '=', True), [9] )

expected( 'born in Montreal; only-best=false', readgedcom.find_individuals( data, 'birt.place', 'Montreal', '=', False), [9, 10] )
