import os
import readgedcom

def show( indi, info, out_file ):
    html = info['html']
    if '&' in html:
       print( indi, info['display'], '/', html, '/', info['unicode'], file=out_file ) 

there = '..' + os.path.sep + '..' + os.path.sep + 'families' + os.path.sep

with open( 'names.out', 'w' ) as outf:
     for family in ['andrea','rogers','smith']:
         ged = there + family + os.path.sep + 'data' + os.path.sep + family + '.ged'

         if os.path.isfile( ged ):
            data = readgedcom.read_file( ged )
            for indi in data[readgedcom.PARSED_INDI]:
                show( indi, data[readgedcom.PARSED_INDI][indi]['name'][0], outf )
         else:
            print( 'coundnt', ged, file=outf )
