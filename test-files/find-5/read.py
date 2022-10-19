import sys
#import pprint
import collections
import readgedcom

options = { 'display-gedcom-warnings': False, 'show-settings': False }

data = readgedcom.read_file( sys.argv[1], options )

def list_subtract( first, subtract ):
    result = []
    for x in first:
        if x not in subtract:
           result.append( x )
    return result


def expected( title, got, wanted ):
    print( '' )
    print( title )
    readgedcom.print_individuals( data, got )
    test_wanted = ['i' + str(i) for i in wanted]
    print( 'expected', test_wanted )
    if collections.Counter( got ) != collections.Counter( test_wanted ):
       print( 'WRONG answer', got )
       return False
    return True


l1 = readgedcom.find_individuals( data, 'name.surname', 'Smith', 'in' )
l2 = readgedcom.find_individuals( data, 'name.given', 'Jane', 'in' )
jane = readgedcom.list_intersection( l1, l2 )
if not expected( 'Jane Smith', jane, [1] ):
   sys.exit(1)

l4 = readgedcom.find_individuals( data, 'parents-of', jane[0], 'exist' )
expected( 'parents of Jane', l4, [2,3] )

l5 = readgedcom.find_individuals( data, 'partnersof', jane[0], 'exist' )
expected( 'partners of Jane', l5, [4,6] )

jane_children = readgedcom.find_individuals( data, 'children of', jane[0], 'exist' )
expected( 'children of Jane', jane_children, [5,7] )

fred = readgedcom.find_individuals( data, 'name.givn', 'Fred' )
expected( 'Fred', fred, [4] )

fred_children = readgedcom.find_individuals( data, 'children of', fred[0], 'exist' )
expected( 'children of Fred', fred_children, [5,8,10] )

children_of_jane_and_fred = readgedcom.list_intersection( jane_children, fred_children )
expected( 'children of Jane+Fred', children_of_jane_and_fred, [5] )

expected( 'parents of Billy', readgedcom.find_individuals( data, 'parents of', children_of_jane_and_fred[0] ), [1,4] )

partners_of_fred = readgedcom.find_individuals( data, 'partners of', fred[0] )
bonnie = list_subtract( partners_of_fred, jane[0] )

expected( 'other partner of Fred', bonnie, [9] )

bonnie_children = readgedcom.find_individuals( data, 'children of', bonnie[0] )

children_of_fred_and_bonnie = readgedcom.list_intersection( fred_children, bonnie_children )
expected( 'children of Fred+Bonnie', children_of_fred_and_bonnie, [8,10] )

expected( 'siblings of Cheryl', readgedcom.find_individuals( data, 'siblings of', children_of_fred_and_bonnie[0] ), [10] )

expected( 'step-siblings of Cheryl', readgedcom.find_individuals( data, 'step-siblings of', children_of_fred_and_bonnie[0] ), [5] )
