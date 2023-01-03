import sys
import pprint
import readgedcom

def show_children( show_all, title, individuals ):
    print( '' )
    print( title )
    the_children = []
    for indi in individuals:
        if 'fams' not in individuals[indi]: # skip the parents
           if show_all:
              the_children.append( indi )
           else:
              if readgedcom.BIRTH_FAM_KEY in individuals[indi]:
                 the_children.append( indi )
    print( sorted( the_children ) )
    return the_children


options = { 'display-gedcom-warnings': True, 'show-settings': False }

data = readgedcom.read_file( sys.argv[1], options )

pprint.pprint( data[readgedcom.PARSED_INDI] )
print( '' )
print( 'family' )
print( '' )
pprint.pprint( data[readgedcom.PARSED_FAM] )


all_children = show_children( True, 'every child', data[readgedcom.PARSED_INDI] )
birth_children = show_children( False, 'only birth children', data[readgedcom.PARSED_INDI] )
print( '' )
print( 'non-birth' )
print( sorted( readgedcom.list_difference( all_children, birth_children ) ) )
