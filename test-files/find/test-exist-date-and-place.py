import sys
import readgedcom

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

print( 'result' )
readgedcom.print_individuals( data, found_both )
