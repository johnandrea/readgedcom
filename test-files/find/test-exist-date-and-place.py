import sys
import collections
import readgedcom


def expected( title, got, wanted ):
    print( '' )
    print( title )
    readgedcom.print_individuals( data, got )
    print( 'expected', wanted )
    test_wanted = ['i' + str(i) for i in wanted]
    if collections.Counter( got ) != collections.Counter( test_wanted ):
       print( 'WRONG answer', got, test_wanted )


data = readgedcom.read_file( 'test-exist-date-and-place.ged' )

print( 'find people with birth place but not a birth date' )

has_place = readgedcom.find_individuals( data, 'birth.place', '', 'exist' )
no_date = readgedcom.find_individuals( data, 'birt.date', '', 'not exist' )

print( 'has place' )
readgedcom.print_individuals( data, has_place )

print( 'no date' )
readgedcom.print_individuals( data, no_date )

# intersection of the two lists
found_both = [item for item in has_place if item in no_date]

expected( 'both', found_both, [3,4] )
