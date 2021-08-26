import sys
import os
import pprint
import readgedcom


#sys.tracebacklimit = 0

if len(sys.argv) < 2:
   print( 'Missing parameters: file', file=sys.stderr )
   sys.exit( 1 )

datafile = sys.argv[1]

if not os.path.isfile( datafile ):
   print( 'Data file does not exist:', datafile, file=sys.stderr )
   sys.exit( 1 )

data = readgedcom.read_file( datafile )

#for indi in data['indi']:
#    print( '' )
#    print( indi )
#    print( indi )
pprint.pprint( data['indi'] )

print( '\n\n----------------------------------------------------\n\n' )

for indi in data['individuals']:
    print( '' )
    print( indi )
    pprint.pprint( data['individuals'][indi] )

readgedcom.output_original( '5.5.1', data, 'old.out' )

readgedcom.set_privatize_flag( data )

readgedcom.output_privatized( data, 'new.out' )
