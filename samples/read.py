import sys
import os
import pprint
import readgedcom

data = readgedcom.read_file( sys.argv[1] )

pprint.pprint( data )
