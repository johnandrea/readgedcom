"""
Create a json file for displaying family as a javascript zoomable sunburst.
Direction can be ancestors or descendants.
Colors can be plain, gender, or 6 levels.

The "6 levels" is a research concept from Yvette Hoitink
https://www.dutchgenealogy.nl/six-levels-ancestral-profiles/
The 6 level values should be stored in the gedcom as a custom event; value 0 to 6.

In order for the display to work, need d3 v4
https://cdnjs.cloudflare.com/ajax/libs/d3/4.13.0/d3.min.js
and the sunburst code
https://gist.github.com/vasturiano/12da9071095fbd4df434e60d52d2d58d
but rather my modification which gets the item color from the data.

This code is released under the MIT License: https://opensource.org/licenses/MIT
Copyright (c) 2023 John A. Andrea
v2.0

No support provided.
"""

import sys
import importlib.util
import argparse
import re
import os

DEFAULT_COLOR = '#e0f3f8'  # level missing or out of range: greyish

LEVEL_COLORS = {0:'#a50026', # unidentified ancestor: redish
                1:'#d73027', # names only: redorangish
                2:'#f46d43', # vital stats: lighter red
                3:'#fdae61', # occ, residence, children, spouses: orangish
                4:'#fee08b', # property, military service: yellowish
                5:'#a6d96a', # genealogical proof standard: light greenish
                6:'#1a9850'  # biography: greenish
               }

PLAIN_COLORS = ['#E5D8BD', '#FFFFB3', '#BEBADA', '#FB8072', '#80B1D3', '#FDB462',
                '#B3DE69', '#FCCDE5', '#D9D9D9', '#BC80BD', '#CCEBC5', '#FFED6F',
                '#E5C494', '#BCBD22', '#CCEBC5' ]

N_PLAIN_COLORS = len( PLAIN_COLORS ) - 1

GENDER_COLORS = {'f':'#FB8072', 'm':'#80B1D3', 'x':'#FFFFB3'}

# these are global flags
color_index = 0
use_levels = False
use_gender = False
levels_tag = None
add_dates = False
n_individuals = 0
levels_stats = {'missing':0, 'not numeric':0, 'out of range':0}
for level in LEVEL_COLORS:
    levels_stats[level] = 0
gender_stats = {'f':0, 'm':0, 'x':0}
indent_more = ' '


def load_my_module( module_name, relative_path ):
    """
    Load a module in my own single .py file. Requires Python 3.6+
    Give the name of the module, not the file name.
    Give the path to the module relative to the calling program.
    Requires:
        import importlib.util
        import os
    Use like this:
        readgedcom = load_my_module( 'readgedcom', '../libs' )
        data = readgedcom.read_file( input-file )
    """
    assert isinstance( module_name, str ), 'Non-string passed as module name'
    assert isinstance( relative_path, str ), 'Non-string passed as relative path'

    file_path = os.path.dirname( os.path.realpath( __file__ ) )
    file_path += os.path.sep + relative_path
    file_path += os.path.sep + module_name + '.py'

    assert os.path.isfile( file_path ), 'Module file not found at ' + str(file_path)

    module_spec = importlib.util.spec_from_file_location( module_name, file_path )
    my_module = importlib.util.module_from_spec( module_spec )
    module_spec.loader.exec_module( my_module )

    return my_module


def get_program_options():
    results = dict()

    directions = [ 'desc', 'descendant', 'descendants',
                   'anc', 'ancestor', 'ancestors' ]
    schemes = [ 'plain', 'gender', 'levels' ]

    results['infile'] = None
    results['start_person'] = None
    results['levels_tag'] = None

    results['scheme'] = schemes[0]
    results['direction'] = directions[0]
    results['dates'] = False
    results['id_item'] = 'xref'

    results['libpath'] = '.'

    arg_help = 'Produce a JSON file for Javascript sunburst display.'
    parser = argparse.ArgumentParser( description=arg_help )

    arg_help = 'Color scheme. Plain or gender. Default: ' + results['scheme']
    parser.add_argument( '--scheme', default=results['scheme'], type=str, help=arg_help )

    arg_help = 'Direction of the tree from the start person. Ancestors or descendants.'
    arg_help += ' Default:' + results['direction']
    parser.add_argument( '--direction', default=results['direction'], type=str, help=arg_help )

    arg_help = 'Show dates along with the names.'
    parser.add_argument( '--dates', default=results['dates'], action='store_true', help=arg_help )

    arg_help = 'How to find the person in the input. Default is the gedcom id "xref".'
    arg_help += ' Othewise choose "type.exid", "type.refnum", etc.'
    parser.add_argument( '--id_item', default=results['id_item'], type=str, help=arg_help )

    # maybe this should be changed to have a type which better matched a directory
    arg_help = 'Location of the gedcom library. Default is current directory.'
    parser.add_argument( '--libpath', default=results['libpath'], type=str, help=arg_help )

    parser.add_argument( 'infile', type=argparse.FileType('r'), help='input GEDCOM file' )
    parser.add_argument( 'start_person', help='Id of person at the center of the display' )
    parser.add_argument( 'levels_tag', nargs='?', help='Tag which holds the levels value. Optional' )

    args = parser.parse_args()

    results['infile'] = args.infile.name
    results['start_person'] = args.start_person.lower().strip()

    # optional
    if args.levels_tag:
       results['levels_tag'] = args.levels_tag.strip()

    results['dates'] = args.dates
    results['id_item'] = args.id_item.lower().strip()
    results['libpath'] = args.libpath

    value = args.direction.lower()
    if value.startswith('anc'):
       results['direction'] = 'anc'

    value = args.scheme.lower()
    if value in schemes:
       results['scheme'] = value

    return results


def looks_like_int( s ):
    return re.match( r'\d\d*$', s )


def fix_names( s ):
    # can't handle "[ em|ndash ? em|ndash ]" as unknown name,
    # use plain dash instead
    return s.replace( '—', '-' )


def get_best_event( tag, indi_data ):
    # just the year
    result = ''
    if tag in indi_data:
       best = 0
       if readgedcom.BEST_EVENT_KEY in indi_data:
          if tag in indi_data[readgedcom.BEST_EVENT_KEY]:
             best = indi_data[readgedcom.BEST_EVENT_KEY][tag]
          if 'date' in indi_data[tag][best]:
             if indi_data[tag][best]['date']['is_known']:
                result = indi_data[tag][best]['date']['min']['year']
    return result


def get_name_parts( indi ):
    name = fix_names( data[i_key][indi]['name'][0]['unicode'] )
    names = name.split()
    first = names[0]
    if add_dates:
       birth = get_best_event( 'birt', data[i_key][indi] )
       death = get_best_event( 'deat', data[i_key][indi] )
       if birth or death:
          name += ' (' + str(birth) +'-'+ str(death) + ')'
    return [ name, first ]


def get_levels_color( indi_data ):
    global levels_stats

    found_tag = False

    result = DEFAULT_COLOR
    if 'even' in indi_data:
       for event in indi_data['even']:
           if levels_tag == event['type']:
              found_tag = True
              value = event['value']
              if looks_like_int( value ):
                 value = int( value )
                 if value in LEVEL_COLORS:
                    result = LEVEL_COLORS[value]
                    levels_stats[value] += 1
                 else:
                    levels_stats['out of range'] += 1
              else:
                 levels_stats['not numeric'] += 1

    if not found_tag:
       levels_stats['missing'] += 1

    return result


def compute_color( gender_guess, indi ):
    global color_index
    global gender_stats

    result = PLAIN_COLORS[color_index]
    color_index = ( color_index + 1 ) % N_PLAIN_COLORS

    if use_gender:
       gender = 'x'
       if 'sex' in data[i_key][indi]:
          sex = data[i_key][indi]['sex'][0].lower()
          if sex in ['m','f']:
             gender = sex
       else:
          if gender_guess == 'wife':
             gender = 'f'
          if gender_guess == 'husb':
             gender = 'm'
       result = GENDER_COLORS[gender]
       gender_stats[gender] += 1

    else:
       if use_levels:
         result = get_levels_color( data[i_key][indi] )

    return result


def get_parents( fam ):
    result = ''
    space = ''
    for parent in ['husb','wife']:
        if parent in data[f_key][fam]:
           parent_id = data[f_key][fam][parent][0]
           if parent_id is not None:
              name_parts = get_name_parts( parent_id )
              result += space + name_parts[0]
              space = '\\n+ '
    return result


def print_key_value( leadin, key, value ):
    print( leadin + '"' + key + '":"' + value + '"', end='' )


def print_person_line( note, indent, needs_comma, indi, color, parents ):
    global n_individuals
    n_individuals += 1

    if needs_comma:
       print( ',' )

    name_parts = get_name_parts( indi )
    detail = name_parts[0]
    first = name_parts[1]

    if note:
       first = note + first
    if parents:
       detail += '\\nParents:\\n' + parents

    new_line = indent
    print_key_value( new_line + '{', 'name', first )
    # comma to and previous item, epace to skip initial open paren
    # line break so that jslint doesn't complain (so much) about long lines
    new_line = ',\n' + indent + ' '
    print_key_value( new_line, 'color', color )
    print_key_value( new_line, 'detail', detail )

    return new_line


def ancestors( first_person, indi, color, needs_comma, indent ):
    first_note = ''
    if first_person:
       first_note = 'Ancestors of\\n'
    line_prefix = print_person_line( first_note, indent, needs_comma, indi, color, '' )

    # assume only biological relationships
    if 'famc' in data[i_key][indi]:
       fam = data[i_key][indi]['famc'][0]

       # these are the person's parents, but the drawing code needs tree node "children"
       print( line_prefix + '"children": [' )

       add_comma = False
       for partner_type in ['wife','husb']:
           if partner_type in data[f_key][fam]:
              partner = data[f_key][fam][partner_type][0]
              ancestors( False, partner, compute_color(partner_type,partner), add_comma, indent + indent_more )
              add_comma = True

       print( '\n', indent, ']}', end='' )

    else:
       print( line_prefix + '"size": 1 }', end='' )


def descendants( first_person, indi, color, needs_comma, indent, parents ):
    first_note = ''
    if first_person:
       first_note = 'Descendants of\\n'
    line_prefix = print_person_line( first_note, indent, needs_comma, indi, color, parents )

    n_children = 0
    needs_comma = False

    if 'fams' in data[i_key][indi]:
       for fam in data[i_key][indi]['fams']:
           parent_info = get_parents( fam )
           if 'chil' in data[f_key][fam]:
              for child in data[f_key][fam]['chil']:
                  n_children += 1

                  if n_children == 1:
                     print( line_prefix + '"children": [' )

                  descendants( False, child, compute_color('x',child), needs_comma, indent + indent_more, parent_info )
                  needs_comma = True

    if n_children > 0:
       print( '\n', indent, ']}', end='' )
    else:
       print( line_prefix + '"size": 1 }', end='' )


def show_stats( label, stats ):
   print( label, 'Count:', file=sys.stderr )
   for name in stats:
       print( name, stats[name], file=sys.stderr )


options = get_program_options()

if options['scheme'] == 'gender':
   use_gender = True
if options['levels_tag']:
   use_gender = False
   use_levels = True
   levels_tag = options['levels_tag']
add_dates = options['dates']
# extra message to prevent confusion with color scheme
if options['scheme'] == 'levels' and not use_levels:
   # even though scheme=levels is not actually required
   print( 'Color scheme set to "levels" but tag for levels value not included.', file=sys.stderr )
   sys.exit(1)

readgedcom = load_my_module( 'readgedcom', options['libpath'] )

read_opts = dict()
read_opts['display-gedcom-warnings'] = False

data = readgedcom.read_file( options['infile'], read_opts )

i_key = readgedcom.PARSED_INDI
f_key = readgedcom.PARSED_FAM

start_ids = readgedcom.find_individuals( data, options['id_item'], options['start_person'] )

if len(start_ids) < 1:
   print( 'Did not find start person:', options['start_person'], 'with', options['id_item'], file=sys.stderr )
   sys.exit(1)
if len(start_ids) > 1:
   print( 'More than one id for start person:', options['start_person'], 'with', options['id_item'], file=sys.stderr )
   sys.exit(1)

print( 'Starting with', get_name_parts( start_ids[0] )[0], file=sys.stderr )

# begin the json for javascript loading
print( 'var loadData=' )

if options['direction'] == 'anc':
   ancestors( True, start_ids[0], compute_color( 'x', start_ids[0] ), False, '' )
else:
   # maybe should get parents for start person instead of currently skipping
   descendants( True, start_ids[0], compute_color( 'x', start_ids[0] ), False, '', '' )

# end
print( ';' )

# show the stats to stderr
print( 'Displayed individuals:', n_individuals, file=sys.stderr )
if use_levels:
   show_stats( 'Level', levels_stats )
if use_gender:
   show_stats( 'Gender', gender_stats )
