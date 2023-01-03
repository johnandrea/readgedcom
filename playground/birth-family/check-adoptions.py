import sys
import pprint
import readgedcom

def get_children( tag, families ):
    the_children = []
    for fam in families:
        if tag in families[fam]:
           for child in families[fam][tag]:
               if child not in the_children:
                  the_children.append( child )
    return the_children

def get_all_chil( families ):
    return get_children( 'all-chil', families )
def get_birth_chil( families ):
    return get_children( 'birth-chil', families )
def get_chil( families ):
    return get_children( 'chil', families )


options = { 'display-gedcom-warnings': True, 'show-settings': False }

data = readgedcom.read_file( sys.argv[1], options )

print( 'all children' )
pprint.pprint( data[readgedcom.PARSED_INDI] )
print( '' )
print( 'family' )
print( '' )
pprint.pprint( data[readgedcom.PARSED_FAM] )

options['only-birth'] = True
birthdata = readgedcom.read_file( sys.argv[1], options )

print( '' )
print( 'birth children' )
pprint.pprint( birthdata[readgedcom.PARSED_INDI] )
print( '' )
print( 'family' )
print( '' )
pprint.pprint( birthdata[readgedcom.PARSED_FAM] )

print( '' )

print( 'method 1' )
all_children = get_chil( data[readgedcom.PARSED_FAM] )
birth_children = get_chil( birthdata[readgedcom.PARSED_FAM] )
print( 'all children', sorted(all_children) )
print( 'birth children', birth_children )
print( 'non-birth', sorted( readgedcom.list_difference( all_children, birth_children ) ) )

print( '' )
print( 'method 2' )
all_children = get_chil( data[readgedcom.PARSED_FAM] )
birth_children = get_birth_chil( data[readgedcom.PARSED_FAM] )
print( 'all children', sorted(all_children) )
print( 'birth children', birth_children )
print( 'non-birth', sorted( readgedcom.list_difference( all_children, birth_children ) ) )

print( '' )
print( 'method 3' )
all_children = get_all_chil( birthdata[readgedcom.PARSED_FAM] )
birth_children = get_birth_chil( birthdata[readgedcom.PARSED_FAM] )
print( 'all children', sorted(all_children) )
print( 'birth children', birth_children )
print( 'non-birth', sorted( readgedcom.list_difference( all_children, birth_children ) ) )
