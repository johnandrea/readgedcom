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

set_privitize_flag( data )

unset_privitize_flag( data )

output_privitized( data, out_file_name )

find_individuals( data, search_tag, search_value, operation )

report_individual_double_facts( data )

report_family_double_facts( data )

```

### Basic usage

A script which will produce a privitized copy.
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

datafile = sys.argv[1]

data = readgedcom.read_file( sys.argv[1] )

found_name = readgedcom.find_individuals( data, 'name', 'Anne ', 'in' )
found_age = readgedcom.find_individuals( data, 'birt.date', '19600101', '<' )

# intersection of the two lists
found_both = [item for item in found_name if item in found_age]

for indi in found_both:
    print( '' )
    print( f )
    print( data[readgedcom.PARSED_INDI][indi]['name'][0]['value'] )
    print( data[readgedcom.PARSED_INDI][indi]['birt'][0]['date']['in'] )
```


A script to output the descendants of a selected individual (by EXID)
into a JSON file.

```
#!/usr/bin/python3

import sys
import json
import readgedcom

datafile = sys.argv[1]
top_exid = sys.argv[2]

data = readgedcom.read_file( sys.argv[1] )

*TO BE UPDATED*
```

## Data structure

The data returned from the function read_file is a Python dict.

## Bug reports

This code is provided with neither support nor warranty.