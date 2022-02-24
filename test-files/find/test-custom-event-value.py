import sys
import readgedcom

data = readgedcom.read_file( 'test-exist-custom-event.ged' )

print( 'find people with value of custom event' )

print( 'everyone with a name' )
everyone = readgedcom.find_individuals( data, 'name', '', 'exist' )
readgedcom.print_individuals( data, everyone )

has_event = readgedcom.find_individuals( data, 'even.blood', 'B', 'in' )
print( 'has B type' )
readgedcom.print_individuals( data, has_event )
