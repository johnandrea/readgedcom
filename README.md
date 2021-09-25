# readgedcom.py

A library for reading and parsing genealogy GEDCOM files.

## Features

- Returns a structure that can be scanned and manipulated.
- Single file.

## Limitations

- Requires Python 3.6+
- GEDCOM versions 5.5, 5.5.1, 7.0.x
- Input file should be well formed. Check with a validator such as
 https://chronoplexsoftware.com/gedcomvalidator/
- Maximum of 5 levels of sub-structures
- No mechanism to output parsed data as a new GEDCOM after manipulation. Instead
 use a genealogy program.

## Installation

No installation process. Copy the file next to your application which uses the library.

## Usage

### Functions:

```
data = read_file( gedcom_file_name )

output_original( data, out_file_name )

set_privatize_flag( data )

unset_privatize_flag( data )

output_privatized( data, out_file_name )

report_individual_double_facts( data )

report_family_double_facts( data )

report_all_descendant_count( data )

report_indi_descendant_count( indi, data )

list_of_indi = find_individuals( data, search_tag, search_value, operation )

print_individuals( data, list_of_indi )
```

### Basic usage

A script which will produce a privatized copy.
```
#!/usr/bin/python3

import sys
import readgedcom

data = readgedcom.read_file( sys.argv[1] )
readgedcom.set_privatize_flag( data )
readgedcom.output_privatized( data, sys.argv[1] + '.new' )
```

A script to display the structure and contents of the data.
```
#!/usr/bin/python3

import sys
import pprint
import readgedcom

data = readgedcom.read_file( sys.argv[1] )
pprint.pprint( data )
```

### Advanced Usage

A script to find anyone with the name "Anne" born before 1960.
```
#!/usr/bin/python3

import sys
import readgedcom

data = readgedcom.read_file( sys.argv[1] )

found_name = readgedcom.find_individuals( data, 'name', 'Anne ', 'in' )
found_age = readgedcom.find_individuals( data, 'birt.date', '19600101', '<' )

# intersection of the two lists
found_both = [item for item in found_name if item in found_age]

readgedcom.print_individuals( data, found_both )
```


A script to output the descendants of a selected individual (by EXID)
into a JSON file.

```
#!/usr/bin/python3

import sys
import json
import readgedcom

def add_person( indi, individuals, families ):
    def get_spouse_name( indi, fam, individuals, families ):
        name = None
        for partner in ['husb','wife']:
            if partner in families[fam]:
               partner_id = families[fam][partner][0]
               # choose the other partner
               if partner_id != indi:
                  name = individuals[partner_id]['name'][0]['display']

        if not name:
           name = readgedcom.UNKNOWN_NAME

        return name

    def add_family( indi, fam, individuals, families ):
        result = dict()
        result['spouse'] = get_spouse_name( indi, fam, individuals, families )
        result['children'] = []
        for child in families[fam]['chil']:
            result['children'].append( add_person( child, individuals, families ) )
        return result

    result = dict()
    result['name'] = individuals[indi]['name'][0]['display']
    result['families'] = []
    # the families in which this person is a parent
    if 'fams' in individuals[indi]:
       for fam in individuals[indi]['fams']:
           result['families'].append( add_family( indi, fam, individuals, families ) )

    return result

datafile = sys.argv[1]
top_exid = sys.argv[2]
out_file = sys.argv[3]

data = readgedcom.read_file( datafile )

found_id = readgedcom.find_individuals( data, 'exid', top_exid )

n = len( found_id )
if n < 1:
   print( 'Didnt find anyone', file=sys.stderr )
elif n > 1:
   print( 'Found more than one person', file=sys.stderr )
else:

   descendants = add_person( found_id[0], data[readgedcom.PARSED_INDI], data[readgedcom.PARSED_FAM] )

   with open( out_file, 'w' ) as outf:
        json.dump( descendants, outf, indent=1 )
```

## Data structure

*The samples/ directory shows examples of the data.*

The data file is read into a dict with the keys of the name of the
zero level gedcom tags:
```
    data['head'] = []
    data['indi'] = []
    data['fam'] = []
    data['trlr'] = []
    etc.
```

Each of those values are lists containing the records
of the tag related to the key. Index 0 = first record,
index 1 = second record, etc.
   Each list value is a dict of the following structure:
```
'in': the line from the input file,
'tag': the tag of the input line, lowercase,
'value': the value on the input line, may be empty,
'parsed' (optional): a dict containing a reference to the parsed section,
'sub': a list of each of the sub-records of the current record.
       These sub-records are of the sane structure
```

There are two other top level keys:
```
   data['individuals'] = dict()
   data['families'] = dict()
```
Those are refered to as the "parsed" sections because they are created
from the matching input file sections into a more easily scanned format.
   Each of those dicts has a key of the indi or family xref (without the "@" sign).
For example:
```
   data['individuals']['i7'] = dict{}
   data['individuals']['i32'] = dict{}
   data['families']['f17'] = dict()
   data['families']['f58'] = dict()
```

The contents of the individual parsed data have the tag as the key into the dict
with a list as the value since most items can take multiple entries. Even single
entry items such as sex are presented as lists to be consistent with the other items.
```
data['individuals']['i7']['name'] = []
data['individuals']['i7']['sex'] = []
data['individuals']['i7']['birt'] = []
data['individuals']['i7']['fams'] = []
data['individuals']['i7']['famc'] = []
```

The primary name will always be index 0, others are alternate names. The sex item will also be at index 0. The index for the "best" birth, death, etc. is discussed later.

Each name is a dict within the list:
```
['name'] = [ {'value':'A Name'}, {'value':'Alt Name'} ]
```

The name "value" is guaranteed to exist, if necessary set to the "unknown" value. The
dict also contains other optional items and a few computed ones:
```
{
 'value': from the input file,
 'givn': from the input file,
 'surn': from the input file,
 'nick', etc. from the input file,
 'display': from the "value" without surname slashes,
 'html': "display" with "special" characters converted to html entities,
 'unicode': "display" with "special" utf-8 chars converted to unicode representation
}
```

Each event (birth, death, burial, etc.) is also a dict with keys of the various
sub-record tags:
```
{
 'date': from the input - parsed into a dict structure,
 'plac': from the input,
 'note': from the input,
 etc.
}
```

Every date is represented as a structure:
```
{
  'in': exactly as in the input file,
  'is_known': has a date been given. If False there is nothing else in the dict,
  'is_range': is the date is a range type (see GEDCOM spec.),
  'malformed': if the date as input is invalid - therefor is of low quality,
  'min': minimum date of the range in a dict structure, 
  'max': maximum date of the tange, or if not a range same values as "min"
}
```

Each one of the "min" and "max" dates themselves is a dict structure:
```
{
  'modifier': empty string, or one of "abt", "bef", "aft", etc.,
  'value': 'yyyymmdd',
  'year': they year only portion as an int
}
```

A birth event could look like this:
```
'birt': [{'date': {'in': '21 APR 1926',
                   'is_known': True,
                   'is_range': False,
                   'malformed': False,
                   'max': {'modifier': '', 'value': '19260421', 'year': 1926},
                   'min': {'modifier': '', 'value': '19260421', 'year': 1926}},
          'plac': 'London'}],
```

## Bug reports

This code is provided with neither support nor warranty.

### Future enhancements

- Collect name type (nickname, aka, etc.) into the individual parsed section.
- Find people pased on custom events.