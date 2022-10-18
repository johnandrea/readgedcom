import sys
#import pprint
import collections
import readgedcom

options = { 'display-gedcom-warnings': False, 'show-settings': False }

data = readgedcom.read_file( sys.argv[1], options )

def expected( title, got, wanted ):
    print( '' )
    print( title )
    readgedcom.print_individuals( data, got )
    print( 'expected', wanted )
    test_wanted = ['i' + str(i) for i in wanted]
    if collections.Counter( got ) != collections.Counter( test_wanted ):
       print( 'WRONG answer', got, test_wanted )
       return False
    return True


l1 = readgedcom.find_individuals( data, 'name.surname', 'Smith', 'in' )
l2 = readgedcom.find_individuals( data, 'name.given', 'Jane', 'in' )
l3 = readgedcom.list_intersection( l1, l2 )
if not expected( 'Jane Smith', l3, [1] ):
   sys.exit(1)

l4 = readgedcom.find_individuals( data, 'parents-of', l3[0], 'exist' )
expected( 'parents of Jane', l4, [2,3] )

l5 = readgedcom.find_individuals( data, 'partnersof', l3[0], 'exist' )
expected( 'partners of Jane', l5, [4,6] )

l6 = readgedcom.find_individuals( data, 'children of', l3[0], 'exist' )
expected( 'children of Jane', l6, [5,7] )

l7 = readgedcom.find_individuals( data, 'name.givn', 'Fred' )
expected( 'Fred', l7, [4] )

l8 = readgedcom.find_individuals( data, 'children of', l7[0], 'exist' )
expected( 'children of Fred', l8, [5,8] )

expected( 'children of Jane+Fred',readgedcom.list_intersection(l6,l8), [5] )
