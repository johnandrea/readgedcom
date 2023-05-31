#!/usr/local/bin/python3

'''
List people who should be considered to be alive in the given year.
For example to see who should be checked for a check_year.

By taking everyone, then eliminating people with rules such as
"born after year", "parents born after year", etc.
   Only the simple tests provide exact results. The others are
"educated guesses" and the test with spouses might not be reliable at all.

This code is released under the MIT License: https://opensource.org/licenses/MIT
Copyright (c) 2023 John A. Andrea

No support provided.
'''

import sys
import argparse
import importlib.util
import os


oldest_possible = 105
youngest_parent = 12
oldest_parent = 80

# add some extra output info and some details to stderr
DEBUG = True
DEBUG_SIMPLE = False


def show_version():
    print( '1.0' )


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

    results['version'] = False
    results['infile'] = None
    results['year'] = 1931
    results['libpath'] = '.'

    arg_help = 'List people in the gedcom who are estimated to be alive in the given year.'
    parser = argparse.ArgumentParser( description=arg_help )

    arg_help = 'Show version then exit.'
    parser.add_argument( '--version', default=results['version'], action='store_true', help=arg_help )

    arg_help = 'Year to consider. Default: ' + str(results['year'])
    parser.add_argument( '--year', default=results['year'], type=int, help=arg_help )

    # maybe this should be changed to have a type which better matched a directory
    arg_help = 'Location of the gedcom library. Default is current directory.'
    parser.add_argument( '--libpath', default=results['libpath'], type=str, help=arg_help )

    parser.add_argument('infile', type=argparse.FileType('r') )

    args = parser.parse_args()

    results['version'] = args.version
    results['year'] = args.year
    results['infile'] = args.infile.name
    results['libpath'] = args.libpath

    return results


def get_vital_date( individual, tag ):
    result = None
    best = 0
    if readgedcom.BEST_EVENT_KEY in individual:
       if tag in individual[readgedcom.BEST_EVENT_KEY]:
          best = individual[readgedcom.BEST_EVENT_KEY][tag]
          if 'date' in individual[tag][best]:
             if individual[tag][best]['date']['is_known']:
                result = individual[tag][best]['date']['max']['year']
    return result

def get_name( individual ):
    result = 'unknown'
    if 'name' in individual:
       result = individual['name'][0]['value']
    return result

def get_xref( individual ):
    return individual['xref']

def get_partners( i ):
    result = []
    if 'fams' in data[i_key][i]:
       for fam in data[i_key][i]['fams']:
           for partner in ['wife','husb']:
               if partner in data[f_key][fam]:
                  p = data[f_key][fam][partner][0]
                  if p != i:
                     result.append( p )
    return result

def get_parents( individual ):
    result = []
    tag = 'birth-famc'
    if tag in individual and individual[tag]:
       fam = individual[tag][0]
       for parent in ['husb', 'wife']:
           if parent in data[f_key][fam]:
              result.append( data[f_key][fam][parent][0] )
    return result

def parents_born_after( parents, year ):
    result = False
    for p in parents:
        birth = people[p]['birth']
        if birth and birth > year:
           result = True
           break
    return result

def parents_died_before( parents, year ):
    result = False
    for p in parents:
        death = people[p]['death']
        if death and death < year:
           result = True
           break
    return result

def ancestors_born_after( i, year, delta ):
    result = False
    parents = get_parents( data[i_key][i] )
    for p in parents:
        birth = people[p]['birth']
        if birth and birth > year:
           result = True
           break
    if not result:
       # more generations
       for p in parents:
           if ancestors_born_after( p, year - delta, delta ):
              result = True
              break
    return result

def descendant_born_before( i, year ):
    result = False
    if 'fams' in data[i_key][i]:
       for fam in data[i_key][i]['fams']:
           for child in data[f_key][fam]['chil']:
               birth = people[child]['birth']
               if birth and birth < year:
                  result = True
                  break
       if not result:
          # more generations
          for fam in data[i_key][i]['fams']:
              for child in data[f_key][fam]['chil']:
                  if descendant_born_before( child, year ):
                     result = True
                     break
    return result

options = get_program_options()

if options['version']:
   show_version()
   sys.exit( 0 )

readgedcom = load_my_module( 'readgedcom', options['libpath'] )

# these are keys into the parsed sections of the returned data structure
i_key = readgedcom.PARSED_INDI
f_key = readgedcom.PARSED_FAM

data_opts = dict()
data_opts['display-gedcom-warnings'] = False
data_opts['exit-on-no-families'] = True
data_opts['exit-on-missing-individuals'] = True
data_opts['exit-on-missing-families'] = True

data = readgedcom.read_file( options['infile'], data_opts )

check_year = options['year']

if DEBUG:
   print( 'Using', check_year, file=sys.stderr )
   if not DEBUG_SIMPLE:
      print( 'Not showing simple tests.', file=sys.stderr )

people = dict()

# this key helps reduce errors on spouse estimation
# in case the died many years apart
because_of_death_date = 'because of death date'

# setup everyone and apply simplest tests

for indi in data[i_key]:
    result = True

    people[indi] = dict()
    people[indi][because_of_death_date] = False

    name = get_name( data[i_key][indi] )

    birth = get_vital_date( data[i_key][indi], 'birt' )
    if birth:
       if birth > check_year:
          result = False
          if DEBUG and DEBUG_SIMPLE:
             print( name, 'born too late', birth, file=sys.stderr )
       if birth < ( check_year - oldest_possible ):
          result = False
          if DEBUG and DEBUG_SIMPLE:
             print( name, 'born too early', birth, file=sys.stderr )

    death = get_vital_date( data[i_key][indi], 'deat' )
    if death and death < check_year:
       result = False
       people[indi][because_of_death_date] = True
       if DEBUG and DEBUG_SIMPLE:
          print( name, 'dead', death, file=sys.stderr )

    people[indi]['name'] = name
    people[indi]['birth'] = birth
    people[indi]['death'] = death
    people[indi]['keep'] = result

# tests on parents

for indi in people:
    if people[indi]['keep']:
       parents = get_parents( data[i_key][indi] )
       if parents:
          result = True

          if result and parents_born_after( parents, check_year - youngest_parent ):
             # this also makes the person born after the check_year
             result = False
             if DEBUG:
                print( people[indi]['name'], 'parents too young', file=sys.stderr )

          if result and parents_died_before( parents, check_year - oldest_parent ):
             # this also makes the person born before the check_year
             result = False
             if DEBUG:
                print( people[indi]['name'], 'parents died before', file=sys.stderr )

          people[indi]['keep'] = result

# multi generation tests

for indi in people:
    if people[indi]['keep']:
       result = True

       if result and ancestors_born_after( indi, check_year - youngest_parent, youngest_parent ):
          # this also makes the person born after the check_year
          result = False
          if DEBUG:
             print( people[indi]['name'], 'ancestors born too early', file=sys.stderr )

       if result and descendant_born_before( indi, check_year - oldest_possible ):
          # this also makes the person born before check_year
          result = False
          if DEBUG:
             print( people[indi]['name'], 'descendants born too late', file=sys.stderr )

       people[indi]['keep'] = result

# depends on results already computed
# but are the least reliable

for indi in people:
    if people[indi]['keep']:
       # no dates, assume similar to spouse
       if not people[indi]['birth'] and not people[indi]['death']:
          partners = get_partners( indi )
          for partner in partners:
              if not people[partner]['keep']:
                 if not people[partner][because_of_death_date]:
                    # otherwise assume birth/ancestors/descendants are similar to spouse
                    people[indi]['keep'] = False
                    if DEBUG:
                       print( people[indi]['name'], 'spouse of removed person', file=sys.stderr )
                       break

n = 0
ok = 0

for indi in people:
    n += 1
    if people[indi]['keep']:
       ok += 1
       xref = get_xref( data[i_key][indi] )
       print( xref, people[indi]['name'], 'ok' )

print( '', file=sys.stderr )
print( 'total', n, file=sys.stderr )
print( 'kept', ok, file=sys.stderr )
