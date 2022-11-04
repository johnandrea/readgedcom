# readgedcom.py

A library for reading and parsing genealogy GEDCOM files.

## Features

- Returns a structure that can be scanned and manipulated.
- Single file.

## Limitations

- Requires Python 3.6+
- GEDCOM versions 5.5, 5.5.1, 7.0.x
  https://gedcom.io/specs/
- Does not support GEDCOM ZIP
- Input file should be well-formed. Check with a validator such as
 https://chronoplexsoftware.com/gedcomvalidator/
- Maximum of 5 levels of sub-structures
- No mechanism to output parsed data as a new GEDCOM after manipulation. Instead,
 use a genealogy program.

## Installation

No installation process. Copy the file next to your application which uses the library.
Or place the readgedcom.py file in a parallel directory and use the load module mechanism to import it:
see the included example code.

## Settings

The optional dict() of settings can change the display of messages, etc.
Either way, the returned data structure will contain a list of generated
messages in data['messages'].

| Name  | Default   | Description |
| :---- | :-------- | :---------- |
| show-settings | False | Print these settings to stderr. |
| display-gedcom-warnings | False | Print GEDCOM input warnings to stderr. |
| exit-on-bad-date | False | Raise exception if malformed date in input, or try to repair. |
| exit-on-unknown-section | False | Raise exception on an unknown GEDCOM section header. |
| exit-on-no-individuals | True | Raise exception  if no individuals found in the input. |
| exit-on-no-families | False | Raise exception if no families found in the input. |
| exit-on-missing-individuals | False | Raise exception if an expected individual not found. |
| exit-on-missing-families | False | Raise exception if an expected family not found. |


### Example Settings

```
opts = dict()
opts['display-gedcom-warnings'] = False
opts['show-settings'] = True
data = readgedcom( filename, opts )
for mess in data['messages']:
    print( '   ', mess, file=sys.stderr )
```


## Usage

### Functions:

```
data = read_file( gedcom_file_name [, settings] )

output_original( data, out_file_name )

set_privatize_flag( data )

unset_privatize_flag( data )

output_privatized( data, out_file_name )

report_counts( data )

report_individual_double_facts( data )

report_family_double_facts( data )

report_all_descendant_count( data )

report_indi_descendant_count( indi, data )

print_individuals( data, list_of_indi )

list_of_indi = find_individuals( data, search_tag, search_value, operation )

list_of_indi = list_intersection( list1, list2, ... )

list_of_indi = list_difference( original, subtract1, subtract2, ... )

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

A script to report the number of individuals, families, and some of their records so long as no errors detected
```
#!/usr/bin/python3

import sys
import readgedcom

opts = dict()
opts['display-gedcom-warnings'] = True

data = readgedcom.read_file( sys.argv[1], opts )
readgedcom.report_counts( data )
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

# people who exist in both lists
found_both = readgedcom.list_intersection( found_name, found_age )

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
   data[readgedcom.PARSED_INDI] = dict()
   data[readgedcom.PARSED_FAM] = dict()
```
Those are referred to as the "parsed" sections because they are created
from the matching input file sections into a more easily scanned format.
   Each of those dicts has a key of the indi or family xref (without the "@" sign).
For example:
```
   data[readgedcom.PARSED_INDI]['i7'] = dict{}
   data[readgedcom.PARSED_INDI]['i32'] = dict{}
   data[readgedcom.PARSED_FAM]['f17'] = dict()
   data[readgedcom.PARSED_FAM]['f58'] = dict()
```

The contents of the individual parsed data have the tag as the key into the dict
with a list as the value since most items can take multiple entries. Even single
entry items such as sex are presented as lists to be consistent with the other items.
```
data[readgedcom.PARSED_INDI]['i7']['name'] = []
data[readgedcom.PARSED_INDI]['i7']['sex'] = []
data[readgedcom.PARSED_INDI]['i7']['birt'] = []
data[readgedcom.PARSED_INDI]['i7']['fams'] = []
data[readgedcom.PARSED_INDI]['i7']['famc'] = []
```

The individual and family parsed sections have a key of "xref" which contains the
original number portion of the input GEDCOM xref (a single integer, not a list).
```
print( data[readgedcom.PARSED_INDI]['i7']['xref'] ) -> 7
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

Each event (birth, death, census, immigration, etc.) is also a dict with keys of the various
sub-record tags:
```
{
 'date': from the input - parsed into a dict structure,
 'plac': from the input,
 'note': from the input,
 etc.
}
```

Note the use of tags as truncated words like in GEDCOM usage, but in lower case. "birt" for birth, "deat" for death, "marr" for marriage, "plac" for place, "chil" for child/children, etc.

Every date is represented as a structure:
```
{
  'in': exactly as in the input file,
  'is_known': has a date been given. If False there is nothing else in the dict,
  'is_range': is the date is a range type (see GEDCOM spec.),
  'malformed': if the date as input is invalid - therefor is of low quality,
  'min': minimum date of the range in a dict structure,
  'max': maximum date of the range, or if not a range same values as "min"
}
```

Each one of the "min" and "max" dates themselves is a dict structure:
```
{
  'modifier': empty string, or one of "abt", "bef", "aft", etc.,
  'value': 'yyyymmdd',
  'year': only the year portion, as an int
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

With only a place recorded, the structure would look like:
```
'birt': [{'date': {'is_known': False},
          'plac': 'London'}],
```
Custom events where a date may not be used or not expected may not have that date/is_known flag so the existance of the "date" key should be tested before checking the "is_known" flag.

There is a case in the GEDCOM spec which allows an event to be known to have occurred
with an unknown date; referred to as a flagged date. 
```
2 DATE Y
```
this code will create a date structure with a "flagged" key of True such as:
```
'date': { 'flagged': True, 'is_known': False }
```
Otherwise, the "flagged" key does not appear; therefor it should be tested after a test
for "is_known".

An Ancestry out-of-spec record like the following is parsed as if it is a flagged date:
```
2 DATE Unknown
```

The parsed families portion has events structured the same as individual events in lists with "best" indexes. Also are 'husb', 'wife' and 'chil' lists; even though 'husb' and 'wife' must occur at most once. 'husb' and 'wife' do not have "best" indexes, and no matter
what your older siblings might tell you there is no "best" child either. The child list is guaranteed to exist, even if it remains empty.

A family structure could be as simple as:
```
{
 'wife': ['i32'],
 'chil': ['i45']
}
```

or a family with children:
```
{
 'wife': ['i32'],
 'husb': ['i73'],
 'chil': ['i45','i46'],
 'marr': [{'date': {'flagged':True, 'is_known':False}}],
 'best-events': {'marr':0}
}
```

If the family record contains relationship tags between a child and a parent they will be collected into the parsed family section. For example if the children in the above family were marked as adopted by both wife and husband:
```
{
  'wife': ['i32'],
  'husb': ['i73'],
  'chil': ['i45','i46'],
  'rel': { 'i45':{'wife':'adopted', 'husb':'adopted'}, 'i46':{'wife':'adopted', 'husb':'adopted'} },
  'marr': [{'date': {'flagged':True, 'is_known':False}}],
  'best-events': {'marr':0}
}
```
Those relationships are currently extracted from RootsMagic specific tags which can take values of "birth", "adopted", "step", "foster", "related", "guardian", "sealed", and "unknown".


## "Best" events

The "best" event indexes are calculated via weights using the proved and disproved flags.
For research purposes multiple entries may exist for any event, even birth and death.
By default the best event is the one first found: index zero. All disproven entries are ignored, they won't be selected even if only disproven entries exist. Proven entries are better than both disputed and un-marked entries. An entry marked as "primary" gets the highest weight - even a non-proven primary entry out-weighs a proven non-primary entry.

The proof/disproved/primary options are specific to RootsMagic exported files.

The best event indexes are contained in a dict in each parsed individual and parsed family
section (unless no events exist) as 'tag name:int
```
{
  'best-events': { 'birth':3, 'death':0 }
}
```

Not every event has a 'best', its for a few events which can't possibly happen more than
once: birth, death, etc. "name" and "sex" are included bacause its possible that research could
have proven/disputed records for those non-event items.
Check the list INDI_SINGLE_EVENTS and for families FAM_SINGLE_EVENTS.

To display a "best" event, the code is something like this:
```
def show_date( indi, tag, indi_data ):
    def show_date_in_event( event_data ):
        if 'date' in event_data and event_data['date']['is_known']:
           print( indi, tag, event_data['date']['in'] )

    if tag in indi_data:
       best = indi_data[readgedcom.BEST_EVENT_KEY].get( tag, 0 )
       show_date_in_event( indi_data[tag][best] )

# every person
for indi in data[readgedcom.PARSED_INDI]:
    show_date( indi, 'birt', data[readgedcom.PARSED_INDI][indi] ) 
```

However for events in general, for example census records which occur multiple times
over multiple years:
```
def show_date( indi, tag, indi_data ):
    def show_date_in_event( event_data ):
        if 'date' in event_data and event_data['date']['is_known']:
           print( indi, tag, event_data['date']['in'] )

    if tag in indi_data:
       if tag in indi_data[readgedcom.BEST_EVENT_KEY]:
          best = indi_data[readgedcom.BEST_EVENT_KEY].get( tag, 0 )
          show_date_in_event( indi_data[tag][best] )
       else:
          # not a single time event, show all
          for event_record in indi_data[readgedcom.BEST_EVENT_KEY][tag]
              show_date_in_event( event_record )

# every person
for indi in data[readgedcom.PARSED_INDI]:
    show_date( indi, 'cens', data[readgedcom.PARSED_INDI][indi] ) 
```

The handling of non-single events with proven/disproved markers will have to be checked in your
own code.

## Using find_individuals

Operations: "=", "not =", "<", "<=", ">", ">=", "in", "not in", "exist", "not exist". Default is "=" and in some cases the operator is ignored.

When selecting dates use a full date as a string in the format "yyyymmdd". Though a day of "00" or month of "00" can be used for less or greater comparisons.

Search tag: Use the name of an individuals fact/event such as "birt", "deat", "name", etc. Sub-tags can be selected like "birt.date", "deat.plac", etc. If a custom event is required, use the prefix "even." as in "even.dnamatch".

Finding relatives: the search tag can be one of "partnersof", "parentsof", "childrenof", "siblingsof" and "step-siblingsof". The operator is ignored and the search value should be a single identifier for an individual in the data.

### Examples

```
# getting all the Ellen Smiths born between 1850 and 1875
list_a = find_individuals( data, 'surn', 'Smith', '=' )
list_b = find_individuals( data, 'givn', 'Ellen", 'in' )
list_c = find_individuals( data, 'birt.date', '18491231', '>' )
list_d = find_individuals( data, 'birt.date', '18760101', '<' )
# Note: use "in" for "givn" rather than "=" because givn might contain a middle name
smiths = list_intersection( list_a, list_b, list_c, list_d )
for indi in smiths:
   print( 'found person' )
   print_individuals( data, [indi] )
   print( 'her partners' )
   print_individuals( find_individuals( data, 'partnersof', indi ) )
   print( 'her children' )
   print_individuals( find_individuals( data, 'childrenof', indi )
```
   

## Bugs

Not every possible unicode character conversion is handled.

## Bug reports

This code is provided with neither support nor warranty.

## Future enhancements

- Collect alternate name parts (aka, etc.) into the individual parsed section.
- Find people based on family events.
- Handle non-biological relationship tags from programs other than RootsMagic (if they exist).
- Use proof flags from programs other than RootsMagic (if they exist).
- Try harder to fix a malformed date. Perhaps fuzzy date parsing.
- Consider using encode/decode for better unicode conversion.
- Consider reading stdin via: for line in io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8'):
- Add option to skip non-biological relationships (adoption, ceremonial, etc.)
- Add ability to locate adoptees.
