import sys
import readgedcom

def show( indi, info, out_file ):
    html = info['html']
    if '&' in html:
       print( indi, info['display'], '/', html, '/', info['unicode'], file=out_file ) 

data = readgedcom.read_file( sys.argv[1] )

with open( 'names.out', 'w' ) as outf:
     for indi in data[readgedcom.PARSED_INDI]:
         show( indi, data[readgedcom.PARSED_INDI][indi]['name'][0], outf )
