import sys
import readgedcom
from pprint import pprint

options = { 'display-gedcom-warnings': False, 'show-settings': False }

data = readgedcom.read_file( sys.argv[1], options )

for e in data[readgedcom.PARSED_INDI]['i1']['even']:
    print( '' )
    pprint( e['date'] )
