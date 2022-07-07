"""
Read a GEDCOM file into a data structure, parse into a dict of
individuals and families for simplified handling; converting to
HTML pages, JSON data, etc.

Public functions:
    data = read_file( gedcom_file_name [, settings ] )

    output_original( data, out_file_name )

    set_privatize_flag( data )

    unset_privatize_flag( data )

    output_privatized( data, out_file_name )

    report_individual_double_facts( data )

    report_family_double_facts( data )

    report_descendant_report( data )

    id_list = find_individuals( data, search_tag, search_value, operation='=' )

    print_individuals( data, id_list )


The input file should be well formed as this code only checks for
a few structural errors. A verification program can be found here:
https://chronoplexsoftware.com/gedcomvalidator/
   Fixable mistakes are corrected as the data is parsed into the data structure.
If the option to output a privatized file is taken, the mistakes from the
original input will also go into the new file.

Some trouble messages go to stderr.
If something really bad is encountered an exception is thrown.

This code handles only the Gregorian calendar with optional epoch setting of BCE.

Specs at https://gedcom.io/specs/

This code is released under the MIT License: https://opensource.org/licenses/MIT
Copyright (c) 2022 John A. Andrea
v1.12.3
"""

import sys
import copy
import re
import datetime
from collections.abc import Iterable

# GEDCOM v7.0 requires this character sequence at the start of the file.
# It may also be present in older versions (RootsMagic does include it).
FILE_LEAD_CHAR = '\ufeff'

# The "x" becomes a "startwsith" comparison
SUPPORTED_VERSIONS = [ '5.5', '5.5.1', '7.0.x' ]

# Section types, listed in order or at least header first and trailer last.
# Some are not valid in GEDCOM 5.5.x, but that's ok if they are not found.
# Including a RootsMagic specific: _evdef, _todo
# Including Legacy specific: _plac_defn, _event_defn
SECT_HEAD = 'head'
SECT_INDI = 'indi'
SECT_FAM = 'fam'
SECT_TRLR = 'trlr'
SECTION_NAMES = [SECT_HEAD, 'subm', SECT_INDI, SECT_FAM, 'obje', 'repo', 'snote', 'sour', '_evdef', '_todo', '_plac_defn', '_event_defn', SECT_TRLR]

# Sections to be created by the parsing
PARSED_INDI = 'individuals'
PARSED_FAM = 'families'

# From GEDCOM 7.0.1 spec pg 40
FAM_EVENT_TAGS = ['anul','cens','div','divf','enga','marb','marc','marl','mars','marr','even']

# From GEDCOM 7.0.1 spec pg 44
INDI_EVENT_TAGS = ['bapm','barm','basm','bles','buri','cens','chra','conf','crem','deat','emig','fact','fcom','grad','immi','natu','ordn','prob','reti','will','adop','birt','chr','even']

# Other individual tags of interest placed into the parsed section,
# in addition to the event tags and of course the name(s)
OTHER_INDI_TAGS = ['sex', 'exid', 'fams', 'famc']

# Other family tag of interest placed into the parsed section,
# in addition to the event tags
FAM_MEMBER_TAGS = ['husb', 'wife', 'chil']
OTHER_FAM_TAGS = []

# Events in the life of a person (or family) which can only occur once
# but might have more than one entry because research is inconclusive.
# These are the ones which will occur in the 'best' lists. See below
# for proved/disproves,etc. and example code.
# A person could be buried multiple times, immigrate multiple times, etc.
# and such entries would be a list and if proven/disproved they would need
# to be checked on their own.
INDI_SINGLE_EVENTS = ['name','sex','birt','deat']
# Assuming that a couple married the second time constiutes a second
# family entry. A couple could for instance get engaged more than once.
FAM_SINGLE_EVENTS = ['marr','div','anul']

# Individual records which are only allowed to occur once.
# However they will still be placed into an array to be consistent
# with the other facts/events.
# An exception will be thrown if a duplicate is found.
# Use of a validator is recommended.
ONCE_INDI_TAGS = ['exid']

# Family items allowed only once.
# See the description of individuals only once.
ONCE_FAM_TAGS = ['husb','wife']

# There are other important records, such as birth and death which are allowed
# to occur more than once (research purposes).
# A meta-structure will be added to each individual pointing to the "best" event,
# the first one, or the first proven one, or the first primary one.
BEST_EVENT_KEY = 'best-events'

# Tags for proof and primary in the case of multiple event records.
# These are RootsMagic specific. A future version might try to detect the product
# which exported the GEDCOM file. Though such options might not be elsewhere.
EVENT_PRIMARY_TAG = '_prim'
EVENT_PRIMARY_VALUE = 'y'
EVENT_PROOF_TAG = '_proof'
EVENT_PROOF_DEFAULT = 'other'
EVENT_PROOF_VALUES = {'disproven':0, EVENT_PROOF_DEFAULT:1, 'proven':2}

# Sub parts to not generally display
LEVEL2_SUB_NAMES = ['npfx', 'nick', 'nsfx']

# Name sub-parts in order of display appearance
LEVEL2_NAMES = ['givn', 'surn'] + LEVEL2_SUB_NAMES

# This code doesn't deal with calendars, but need to know what to look for
# in case of words before a date.
CALENDAR_NAMES = [ 'gregorian', 'hebrew', 'julian', 'french_r' ]

# From GEDCOM 7.0.3 spec pg 21
DATE_MODIFIERS = [ 'abt', 'aft', 'bef', 'cal', 'est' ]

# Alternate date modifiers which are not in the spec but might be in use.
# Give their allowed replacement.
# Ancestry may place a period after the abbreviation.
ALT_DATE_MODIFIERS = {'about':'abt', 'after':'aft', 'before':'bef',
                      'ca':'abt', 'circa':'abt',
                      'calculated':'cal', 'estimate':'est', 'estimated':'est',
                      'abt.':'abt', 'aft.':'aft', 'bef.':'bef',
                      'ca.':'abt', 'cal.':'cal', 'est.':'est' }

# The semi-standard replacement for an unknown name
UNKNOWN_NAME = '[-?-]'  #those are supposted to be en-dashes - will update later

# Names. zero included in the zero'th index location for one-based indexing
MONTH_NAMES = ['zero','jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec']

# Month name to number. "may" is not included twice.
MONTH_NUMBERS = {'jan':1, 'feb':2, 'mar':3, 'apr':4, 'may':5, 'jun':6,
				'jul':7, 'aug':8, 'sep':9, 'oct':10, 'nov':11, 'dec':12,
				'january':1, 'february':2, 'march':3, 'april':4, 'june':6,
				'july':7, 'august':8, 'september':9, 'october':10, 'november':11, 'december':12}

# Bad dates can be tried to be fixed or cause exit
DATE_ERR = 'Malformed date:'

# The message for data file troubles
DATA_ERR = 'GEDCOM error. Use a validator. '
DATA_WARN = 'Warning. Use a validator. '

# What to do with unknown sections
UNK_SECTION_ERR = 'Unknown section: '
UNK_SECTION_WARN = 'Warning. Ignoring unknown section:'

# dd mmm yyyy - same format as gedcom
TODAY = datetime.datetime.now().strftime("%d %b %Y")

# Settings for the privatize flag
PRIVATIZE_FLAG = 'privatized'
PRIVATIZE_OFF = 0
PRIVATIZE_MIN = PRIVATIZE_OFF + 1
PRIVATIZE_MAX = PRIVATIZE_MIN + 1

# Some checking to help prevent typos. Failure will throw an exception.
# I don't imagine the checking causes much of a performance hit.
# This is not a passed in as a setting.
SELF_CONSISTENCY_CHECKS = True
SELF_CONSISTENCY_ERR = 'Program code inconsistency:'

# The detected version of the input file. Treat as a global.
version = ''

# This is the operational settings. Treat as a global
run_settings = dict()

# A place to save all messages which will be copied into the output data. Treat as a global.
all_messages = []

# This becomes a global into the convert routine
unicode_table = dict()


def list_intersection( *lists ):
    """ For use with find_individuals results.
        Return the intersection of all the given lists. """
    result = []
    for l in lists:
        if isinstance( l, Iterable ):
           if result:
              r = result
              result = [item for item in l if item in r]
           else:
              result = l
    return result


def setup_unicode_table():
    """ Define utf-8 characters to convert to unicode characters.
    Favouring (Latin) English and French names.
    Including backslash and quotes to prevent trouble in output as quoted strings, etc.
    """
    # https://www.cl.cam.ac.uk/~mgk25/ucs/quotes.html
    # https://www.compart.com/en/unicode/block

    lookup_table = dict()

    lookup_table['back slash'] = [ '\\', '\\u005c' ]
    lookup_table['back quote'] = [ '`', '\\u0060' ]
    lookup_table['double quote'] = [ '"', '\\u0022' ]
    lookup_table['single quote'] = [ "'", '\\u0027' ]
    lookup_table['en dash'] = [ '\xe2\x80\x93', '\\u2013' ]
    lookup_table['em dash'] = [ '\xe2\x80\x94', '\\u2014' ]
    lookup_table['A grave'] = [ '\xc0', '\\u00c0' ]
    lookup_table['a grave'] = [ '\xe0', '\\u00e0' ]
    lookup_table['A acute'] = [ '\xc1', '\\u00c1' ]
    lookup_table['a acute'] = [ '\xe1', '\\u00e1' ]
    lookup_table['A circumflex'] = [ '\xc2', '\\u00c2' ]
    lookup_table['a circumflex'] = [ '\xe2', '\\u00e2' ]
    lookup_table['C cedilia'] = [ '\xc7', '\\u00c7' ]
    lookup_table['c cedilia'] = [ '\xe7', '\\u00e7' ]
    lookup_table['E acute'] = [ '\xc9', '\\u00c9' ]
    lookup_table['e acute'] = [ '\xe9', '\\u00e9' ]
    lookup_table['E grave'] = [ '\xc8', '\\u00c8' ]
    lookup_table['e grave'] = [ '\xe8', '\\u00e8' ]
    lookup_table['I grave'] = [ '\xcc', '\\u00cc' ]
    lookup_table['i grave'] = [ '\xec', '\\u00ec' ]
    lookup_table['I acute'] = [ '\xcd', '\\u00cd' ]
    lookup_table['i acute'] = [ '\xed', '\\u00ed' ]
    lookup_table['I circumflex'] = [ '\xce', '\\u00ce' ]
    lookup_table['i circumflex'] = [ '\xee', '\\u00ee' ]
    lookup_table['O grave'] = [ '\xd2', '\\u00d2' ]
    lookup_table['o grave'] = [ '\xf2', '\\u00f2' ]
    lookup_table['O acute'] = [ '\xd3', '\\u00d3' ]
    lookup_table['o acute'] = [ '\xf3', '\\u00f3' ]
    lookup_table['O circumflex'] = [ '\xd4', '\\u00d4' ]
    lookup_table['o circumflex'] = [ '\xf4', '\\u00f4' ]
    lookup_table['O diaresis'] = [ '\xd6', '\\u00d6' ]
    lookup_table['o diaresis'] = [ '\xf6', '\\u00f6' ]
    lookup_table['U grave'] = [ '\xd9', '\\u00d9' ]
    lookup_table['u grave'] = [ '\xf9', '\\u00f9' ]
    lookup_table['U acute'] = [ '\xda', '\\u00da' ]
    lookup_table['u acute'] = [ '\xfa', '\\u00da' ]
    lookup_table['U circumflex'] = [ '\xdb', '\\u00db' ]
    lookup_table['u circumflex'] = [ '\xfb', '\\u00fb' ]
    lookup_table['U diaresis'] = [ '\xdc', '\\u00dc' ]
    lookup_table['u diaresis'] = [ '\xfc', '\\u00fc' ]
    lookup_table['Sharp'] = [ '\xdf', '\\u00df' ]

    return lookup_table


def convert_to_unicode( s ):
    """ Convert common utf-8 encoded characters to unicode for the various display of names etc.
        The pythonic conversion routines don't seem to do the job.
    """
    text = s.strip()
    for item in unicode_table:
        text = text.replace( unicode_table[item][0], unicode_table[item][1] )
    return text


def convert_to_html( s ):
    """ Convert common utf-8 encoded characters to html for the various display of names etc."""
    # https://dev.w3.org/html5/html-author/charref
    text = s.strip()
    text = text.replace('&','&smp;').replace('<','&lt;').replace('>','&gt;' )
    text = text.replace('"','&quot;').replace("'",'&apos;')
    text = text.replace('`','&#96;').replace('\\','&bsol;')
    # encode generates a byte array, decode goes back to a string
    text = text.encode( 'ascii', 'xmlcharrefreplace' ).decode( 'ascii' )
    return text


def print_warn( message ):
    global all_messages
    all_messages.append( message )
    if run_settings['display-gedcom-warnings']:
       print( message, file=sys.stderr )


def concat_things( *args ):
    """ Behave kinda like a print statement: convert all the things to strings.
        Return the large concatinated string. """
    result = ''
    space = ''
    for arg in args:
        result += space + str(arg).strip()
        space = ' '
    return result


def setup_settings( settings=None ):
    """ Set the settings which control how the program operates.
        Return a dict with the defaults or the user supplied values. """

    new_settings = dict()

    if settings is None:
       settings = dict()
    if not isinstance( settings, dict ):
       settings = dict()

    defaults = dict()
    defaults['show-settings'] = False
    defaults['display-gedcom-warnings'] = False
    defaults['exit-on-bad-date'] = False
    defaults['exit-on-unknown-section'] = False
    defaults['exit-on-no-individuals'] = True
    defaults['exit-on-no-families'] = False
    defaults['exit-on-missing-individuals'] = False
    defaults['exit-on-missing-families'] = False

    for item in defaults:
        setting = defaults[item]
        if item in settings:
           if isinstance( settings[item], type(setting) ):
              setting = settings[item]
        new_settings[item] = setting

    if new_settings['show-settings']:
       for item in new_settings:
           print( 'Setting', item, '=', new_settings[item], file=sys.stderr )

    return new_settings


def string_like_int( s ):
    """ Given a string, return test if it contains only digits. """
    if re.search( r'\D', s ):
       return False
    return True


def yyyymmdd_to_date( yyyymmdd ):
                     #01234567
    """ Return the human form of dd mmm yyyy. """
    y = yyyymmdd[:4]
    m = yyyymmdd[4:6]
    d = yyyymmdd[6:]

    return d + ' ' + MONTH_NAMES[int(m)] + ' ' + y


def comparable_before_today( years_ago ):
    """ Given a number of years before now, return yyyymmdd as that date."""
    # The leap year approximation is ok, this isn't for exact comparisons.
    leap_days = years_ago % 4
    old_date = datetime.datetime.now() - datetime.timedelta( days = (365 * years_ago) + leap_days )
    return '%4d%02d%02d' % ( old_date.year, old_date.month, old_date.day )


def strip_lead_chars( line ):
    """ Remove the file start characters from the file's first line."""
    return line.replace( FILE_LEAD_CHAR, '' )


def month_name_to_number( month_name ):
    """ Using the dict of month names, return the int month number, else zero if not found."""
    if month_name and month_name.lower() in MONTH_NUMBERS:
       return MONTH_NUMBERS[month_name.lower()]
    return 0


def add_file_back_ref( file_tag, file_index, parsed_section ):
    """ Map back from the parsed section to the correcponding record in the
        data read from directly from the input file."""
    parsed_section['file_record'] = { 'key':file_tag, 'index':file_index }


def copy_section( from_sect, to_sect, data ):
    """ Copy a portion of the data from one section to another."""
    if from_sect in SECTION_NAMES:
       if from_sect in data:
          data[to_sect] = copy.deepcopy( data[from_sect] )
       else:
          data[to_sect] = []
    else:
       print_warn( concat_things( 'Cant copy unknown section:', from_sect ) )


def extract_indi_id( tag ):
    """ Use the id as the xref which the spec. defines as "@" + xref + "@".
        Rmove the @ and change to lowercase leaving the "i"
        Ex. from "@i123@" get "i123"."""
    return tag.replace( '@', '' ).lower().replace( ' ', '' )


def extract_fam_id( tag ):
    """ Sumilar to extract_indi_id. """
    return tag.replace( '@', '' ).lower().replace( ' ', '' )


def output_sub_section( level, outf ):
    """ Print a portion of the data to the output file handle."""
    print( level['in'], file=outf )
    for sub_level in level['sub']:
        output_sub_section( sub_level, outf )


def output_section( section, outf ):
    """ Output a portion of the data to the given file handle. """
    for level in section:
        output_sub_section( level, outf )


def output_original( data, file ):
    """
    Output the original data (unmodified) to the given file handle.
    Essentially copying the input gedcom file.

    Parameters:
        data: data structure retured from the function read_file.
        file: name of the output file.
    """

    assert isinstance( data, dict ), 'Non-dict passed as the data parameter.'
    assert isinstance( file, str ), 'Non-string passed as the filename parameter.'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'

    global version

    with open( file, 'w' ) as outf:
         if not version.startswith( '5' ):
            print( FILE_LEAD_CHAR, end='' )
         for sect in SECTION_NAMES:
             if sect in data:
                output_section( data[sect], outf )


def get_parsed_year( data ):
    """ Return only the year portion from the given data section, or an empty string.
        The "data" should be the part of the parsed section down to the "date" index."""

    value = ''

    if data['is_known']:
       modifier = data['min']['modifier'].upper()
       if modifier:
          value = modifier + ' '
       value += str( data['min']['year'] )
       if data['is_range']:
          value += ' '
          modifier = data['max']['modifier'].upper()
          if modifier:
             value += modifier + ' '
          value += str( data['max']['year'] )

    return value


def get_reduced_date( lookup, parsed_data ):
    """ Return the date for the given data section, or an empty string.
        The event to lookfor is in lookup['key'] and lookup['index']
        where the index is the i'th instance of the event named by the key. """

    # It must exist in the parsed data if the event existed in the input file
    # except that it might exist in an empty state with sub-records

    value = ''

    k = lookup['key']
    i = lookup['index']

    if 'date' in parsed_data[k][i]:
       value = get_parsed_year( parsed_data[k][i]['date'] )

    return value


def output_section_no_dates( section, outf ):
    """ Print a section of the data to the file handle, skipping any date sub-sections."""
    for level in section:
        if level['tag'] != 'date':
           print( level['in'], file=outf )
           output_section_no_dates( level['sub'], outf )


def output_privatized_section( level0, priv_setting, event_list, parsed_data, outf ):
    """ Print data to the given file handle with the data reduced based on the privatize setting.
        'level0' is the un-parsed section correcponding to the
        'parsed_data' section for an individual or family.
        'event_list' contains the names of events which are likely to contain dates."""

    print( level0['in'], file=outf )
    for level1 in level0['sub']:
        parts = level1['in'].split( ' ', 2 )
        tag1 = parts[1].lower()
        if tag1 in event_list:
           if priv_setting == PRIVATIZE_MAX:
              if tag1 == 'even':
                 # This custom event is output differently than the regular events
                 # such as birt, deat, etc.
                 print( level1['in'], file=outf )
                 # continue, but no dates
                 output_section_no_dates( level1['sub'], outf )
              else:
                 # For full privatization this event and subsection is skipped
                 # except it must be shown that the event is flagged as existing
                 print( parts[0], parts[1], 'Y', file=outf )

           else:
              # otherwise, partial privatization, reduce the detail in the dates
              print( level1['in'], file=outf )
              for level2 in level1['sub']:
                  parts = level2['in'].split( ' ', 2 )
                  tag2 = parts[1].lower()
                  if tag2 == 'date':
                     # use the partly hidden date
                     print( parts[0], parts[1], get_reduced_date( level1['parsed'], parsed_data), file=outf )
                  else:
                     print( level2['in'], file=outf )
                  # continue with the rest
                  output_section( level2['sub'], outf )

        else:
           # Not an event. A date in here is accidental information
           output_sub_section( level1, outf )


def output_privatized_indi( level0, priv_setting, data_section, outf ):
    """ Print an individual to the output handle, in privatized format."""
    output_privatized_section( level0, priv_setting, INDI_EVENT_TAGS, data_section, outf )


def output_privatized_fam( level0, priv_setting, data_section, outf ):
    """ Print a family to the output handle, in privatized format."""
    output_privatized_section( level0, priv_setting, FAM_EVENT_TAGS, data_section, outf )


def check_section_priv( item, data ):
    """ Return the value of the privatization flag for the given individual or family."""
    return data[item][PRIVATIZE_FLAG]


def check_fam_priv( fam, data ):
    """ Return the value of the privatization flag for the given family. """
    return check_section_priv( extract_fam_id( fam ), data[PARSED_FAM] )


def check_indi_priv( indi, data ):
    """ Return the value of the privatization flag for the given individual. """
    return check_section_priv( extract_indi_id( indi ), data[PARSED_INDI] )


def output_privatized( data, file ):
    """"
    Print the data to the given file name. Some data will not be output.

    Parameters:
        data: the data structure returned from the function read_file.
        file: name of the file to contain the output.

    See the function set_privatize_flag for the settings.
    set_privatize_flag is optional, but should be called if this output function is used.
    """

    assert isinstance( data, dict ), 'Non-dict passed as data parameter'
    assert isinstance( file, str ), 'Non-string passed as the filename parameter'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'

    # Working with the original input lines
    # some will be dropped and some dates will be modified
    # based on the privatize setting for each person and family.

    isect = PARSED_INDI
    fsect = PARSED_FAM

    with open( file, 'w' ) as outf:
         if not version.startswith( '5' ):
            print( FILE_LEAD_CHAR, end='' )

         for sect in SECTION_NAMES:
             if sect in data:
                if sect == SECT_INDI:
                   for section in data[sect]:
                       indi = extract_indi_id( section['tag'] )
                       priv_setting = check_indi_priv( indi, data )
                       if priv_setting == PRIVATIZE_OFF:
                          output_sub_section( section, outf )
                       else:
                          output_privatized_indi( section, priv_setting, data[isect][indi], outf )

                elif sect == SECT_FAM:
                   for section in data[sect]:
                       fam = extract_fam_id( section['tag'] )
                       priv_setting = check_fam_priv( fam, data )
                       if priv_setting == PRIVATIZE_OFF:
                          output_sub_section( section, outf )
                       else:
                          output_privatized_fam( section, priv_setting, data[fsect][fam], outf )

                else:
                   output_section( data[sect], outf )


def confirm_gedcom_version( data ):
    """ Return the GEDCOM version number as detected in the input file.
        Raise ValueError exception if no version or unsupported version."""

    # This should be called as soon as a non-header section is found
    # to ensure the remainder of the file can be handled.
    # The old versions (pre 5.5) have less well defined structures.

    version = None

    sect = SECTION_NAMES[0] # head

    if data[sect]:
       for level1 in data[sect][0]['sub']:
           if level1['tag'] == 'gedc':
              for level2 in level1['sub']:
                  if level2['tag'] == 'vers':
                     version = level2['value']
                     break

       if version:
          ok = False
          for supported in SUPPORTED_VERSIONS:
              if 'x' in supported:
                 # ex: change "7.0.x" to "7.0." and see if that matches "7.0.3"
                 with_wildcard = re.sub( r'x.*', '', supported )
                 if version.startswith( with_wildcard ):
                    ok = True
                    break
              else:
                 if version == supported:
                    ok = True
                    break
          if not ok:
             raise ValueError( 'Version not supported:' + str(version) )
       else:
          raise ValueError( 'Version not detected in header section' )
    else:
       raise ValueError( 'Header section not detected' )

    return version


def line_values( input_line ):
    """
    For the given line from the GEDCOM file return a dict of
        {
          in: exact input line from the file,
          tag: the second item on the input line lowercased,
          value: input line after tag (or None),
          sub: empty array to be used for sub elements
        }.
    """

    # example:
    # 1 CHAR IBM WINDOWS
    # becomes
    # { in:'1 CHAR IBM WINDOWS', tag:'char', value:'IBM WINDOWS', sub:[] }
    #
    # example:
    # 0 @I32@ INDI
    # becomes
    # { in:'0 @I32@ INDI', tag:'@i32@', value:'INDI', sub:[] }
    #
    # example:
    # 2 DATE 14 DEC 1895
    # becomes
    # { in:'2 DATE 14 DEC 1895', tag:'date', value:'14 DEC 1895', sub:[] }

    data = dict()

    parts = input_line.split(' ', 2)

    data['in'] = input_line
    data['tag'] = parts[1].lower()
    value = None
    if len(parts) > 2:
       value = parts[2]
    data['value'] = value
    data['sub'] = []

    return data


def date_to_comparable( original ):
    """
    Convert a date to a string of format 'yyyymmdd' for comparison with other dates.
    Returns a dict:
       ( 'value':'yyyymmdd', 'malformed':boolean, 'add_abt_modifier':boolean )

    where "malformed" is True if the original had to be repaired to be usable,
    where "add_abt_modifier" means that "ABT" must be added because the
    date was not full (only year, only month+year) or was malformed

    The prefix may contain 'gregorian',
    the suffix may contain 'bce',
    otherwise the date should be well formed, i.e. valid digits and valid month name.
    See the GEDCOM spec.

    A malformed portion may be converted to a "1", or might throw an exception
    if the crash_on_bad_date flag is True (default False).

    ValueError is thrown for a non-gregorian calendar.
    """

    # examples:
    # '7 nov 1996' returns '19961107'
    # 'nov 1996' returns 'ABT 19961101'
    # '1996' returns 'ABT 19960101'
    # '' returns ''
    # 'seven nov 1996' returns 'ABT 19961101' or throws ValueError
    # '7 never 1996' returns 'ABT 19960107' or throws ValueError
    # '7 nov ninesix' returns 'ABT 00011107' or throws ValueError

    default_day = 1
    default_month = 1
    default_year = 1

    exit_bad_date = run_settings['exit-on-bad-date']

    result = None
    malformed = False
    add_abt_modifier = False

    date = original.lower().replace( '  ', ' ' ).replace( '  ', ' ' ).strip()
    date = re.sub( r'^gregorian', '', date ).strip() #ignore this calendar
    date = re.sub( r'bce$', '', date ).strip() #ignore this epoch

    if date:

       parts = date.split()

       if parts[0] in CALENDAR_NAMES:
          raise ValueError( 'Cannot handle calendar: ' + str(parts[0]) )

       day = default_day
       month = default_month
       year = default_year

       if len( parts ) == 1:
          year = parts[0]
          add_abt_modifier = True

       elif len( parts ) == 2:
          month = parts[0]
          year = parts[1]
          add_abt_modifier = True

       elif len( parts ) == 3:
          day = parts[0]
          month = parts[1]
          year = parts[2]

       else:
          if exit_bad_date:
             raise ValueError( DATE_ERR + ':' + str(original) )
          malformed = True
          print_warn( concat_things( DATE_ERR, original, ':setting to', year, month, day ) )
          add_abt_modifier = True

       if isinstance(day,str):
          #i.e. has been extracted from the given date string
          if string_like_int( day ):
             day = int( day )
             if day < 1 or day > 31:
                day = default_day
                if exit_bad_date:
                   raise ValueError( DATE_ERR + ':' + str(original) )
                malformed = True
                print_warn( concat_things(DATE_ERR, original, ':setting day to', day ) )
                add_abt_modifier = True

          else:
             if exit_bad_date:
                raise ValueError( DATE_ERR + ':' + str(original) )
             day = default_day
             malformed = True
             print_warn( concat_things( DATE_ERR, original, ':setting day to', day ) )
             add_abt_modifier = True

       if isinstance(month,str):
          #i.e. has been extracted from the given date string
          if month in MONTH_NUMBERS:
             month = month_name_to_number( month )
          else:
             malformed = True
             print( DATE_ERR, original, ': attempting to correct', file=sys.stderr )
             month = month.replace( '-', '' ).replace( '.', '' )
             if month in MONTH_NUMBERS:
                month = month_name_to_number( month )
             else:
                if exit_bad_date:
                   raise ValueError( DATE_ERR + ':' + str(original) )
                month = default_month
                print_warn( concat_things( DATE_ERR, original, ':setting month to number', month ) )
             add_abt_modifier = True

       if isinstance(year,str):
          #i.e. has been extracted from the given date string
          if string_like_int( year ):
             year = int( year )
          else:
             malformed = True
             # don't throw an exception yet
             print_warn( concat_things( DATE_ERR, original, ':attempting to correct' ) )
             # Ancestry mistakes
             year = year.replace( '-', '' ).replace( '.', '' )
             if string_like_int( year ):
                year = int( year )
             else:
                if exit_bad_date:
                   raise ValueError( DATE_ERR + ':' + str(original) )
                year = default_year
                print_warn( concat_things( DATE_ERR, original, ':setting year to:', year ) )
             add_abt_modifier = True

       result = '%04d%02d%02d' % ( year, month, day )

    return { 'value':result, 'malformed':malformed, 'add_abt_modifier':add_abt_modifier }


def date_comparable_results( original, key, date_data ):
    """ Get the results from the to-comparable conversion and set into the date data values."""
    results = date_to_comparable( original )

    date_data[key]['value'] = results['value']

    # Set true if false
    if not date_data['malformed']:
       date_data['malformed'] = results['malformed']

    #print( 'date data:', date_data, ':', file=sys.stderr ) #debug

    if results['add_abt_modifier']:
       if not date_data['min']['modifier']:
          date_data['min']['modifier'] = 'ABT'
       if not date_data['max']['modifier']:
          date_data['max']['modifier'] = 'ABT'


def date_to_structure( original ):
    """
    Given a GEDCOM date (see 7.0.1 spec pg 22) return a dict with a structure of the date.
        {
          is_known: boolean, False for an empty date,
          in: copy of original date from the input file,
          malformed: True if the original was "repaired" - meaning quality is low,
          is_range: True if date spec'ed as datePeriod or a between/and dateRange,
          min: { modifier:, value:, year: },
          max: { modifier:, value:, year: }
        }
    where modifier is one of '', 'bef', 'aft', 'abt', etc.
    where value is a string in comparable format 'yyyymmdd',
    and year is an int.

    If date is not a range, min and max are set to the same values.
    If is_known is False, it is the only item in the returned dict.
    """

    value = dict()
    value['is_known'] = False
    given = None

    if original:
       given = original.lower().replace( '  ', ' ' ).replace( '  ', ' ' ).strip()

    if given:
       value['is_known'] = True

       value['is_range'] = False
       value['in'] = original
       value['malformed'] = False
       value['min'] = dict()
       value['max'] = dict()
       value['min']['modifier'] = ''
       value['max']['modifier'] = ''

       # Ranges cannot contain modifiers such as before, after, etc.,
       # use the "from" / "to", etc. instead

       if 'from ' in given and ' to ' in given:
          value['is_range'] = True
          parts = given.replace( 'from ', '' ).split( ' to ' )
          date_comparable_results( parts[0], 'min', value )
          date_comparable_results( parts[1], 'max', value )
          value['min']['modifier'] = 'from'
          value['max']['modifier'] = 'to'

       elif 'bet ' in given and ' and ' in given:
          value['is_range'] = True
          parts = given.replace( 'bet ', '' ).split( ' and ' )
          date_comparable_results( parts[0], 'min', value )
          date_comparable_results( parts[1], 'max', value )
          value['min']['modifier'] = 'bet'
          value['max']['modifier'] = 'and'

       elif given.startswith( 'to ' ):
          # Seems like this specifies everything up to the date
          # why use this instead of 'before'
          date_comparable_results( given.replace( 'to ', '' ), 'min', value )
          value['min']['modifier'] = 'to'
          for item in ['value','modifier']:
              value['max'][item] = value['min'][item]

       else:
          parts = given.split()

          if parts[0] in DATE_MODIFIERS:
             value['min']['modifier'] = parts[0]
             given = given.replace( parts[0] + ' ', '' )
          elif parts[0] in ALT_DATE_MODIFIERS:
             value['min']['modifier'] = ALT_DATE_MODIFIERS[parts[0]]
             given = given.replace( parts[0] + ' ', '' )

          date_comparable_results( given, 'min', value )

          for item in ['value','modifier']:
              value['max'][item] = value['min'][item]

       for item in ['min','max']:
           if value[item]['value']:
              value[item]['year'] = int( value[item]['value'][0:4] )
           else:
              value[item]['year'] = None

    return value


def get_note( level2 ):
    """ Return the note of an event. Continuation lines concatinated to a single string."""

    # Pre version 7.0 the note lines were short; requiring continuation lines.
    #
    # There are rules about adding spaces and not stripping spaces from continuation lines.
    # I'm not sure I'm handling that correctly.
    #
    # GEDCOM 7.0.1 introduces the "cont" tag which might require newlines between records.

    value = ''
    if level2['value']:
       value += level2['value']
    for level3 in level2['sub']:
        tag = level3['tag']
        if tag in ['conc','cont']:
           if level3['value']:
              value += level3['value']
           else:
              value += ' '

    return value.replace( '  ', ' ' )


def set_best_events( single_time_list, out_data ):
    """ For each event with multiple instances within a single individual or family
        Set the index of the "best" instance based on the proof and primary settings.
        Disproven events will not become a best selected.
        The computation here depends on the disproved/default/proved values
        set to 0,1,2 though -1,1,2 would also work. """

    # Note that custom event records with the tag "even" are not included
    # because of the the associated even.type

    out_data[BEST_EVENT_KEY] = dict()

    # Initial value is smaller than the smallest of all in order for the first test
    # to pick up the first item tested.
    smallest = min( EVENT_PROOF_VALUES.values() ) - 1

    for tag in single_time_list:
        if tag in out_data:

           # Find the best: disproven having lowest value, proven is highest
           value_best = smallest
           found_best = 0

           for i, section in enumerate( out_data[tag] ):
               value = EVENT_PROOF_VALUES[EVENT_PROOF_DEFAULT]
               if EVENT_PROOF_TAG in section:
                  proof_setting = section[EVENT_PROOF_TAG].lower()
                  if proof_setting in EVENT_PROOF_VALUES:
                     value = EVENT_PROOF_VALUES[proof_setting]
                  # just the existance of this tag is good enough
                  if EVENT_PRIMARY_TAG in section:
                     # even better is primary, but disproven gets no better
                     value *= 10
               if value > value_best:
                  value_best = value
                  found_best = i

           # must be better than disproven to get included in the list of best events
           if value_best > EVENT_PROOF_VALUES['disproven']:
              out_data[BEST_EVENT_KEY][tag] = found_best


def handle_event_dates( value ):
    """ Parse a event date. Special cases could be handled in here."""
    return date_to_structure( value )


def handle_event_tag( tag, level1, out_data ):
    """ Parse an individual or family event record."""

    # An event record looks like this
    #
    #1 BIRT
    #2 DATE 14 DEC 1895
    #2 PLAC York Cottage, Sandringham, Norfolk, England
    #
    # Its also possible to have an event flagged as known without details
    #
    #1 DEAT Y
    #
    # or the date can be empty if a sub-structure is given
    #1 BURI
    #2 DATE
    #3 PHRASE Week after death.
    #
    # and exports from Ancestry break the rules by putting notes on the event line
    #
    #1 BIRT Details given in church records.

    values = dict()

    ancestry_note = None

    value = level1['value']
    if value:
       if value.lower() in ['y','unknown']:
          # The value of "unknown" is an Ancestry out-of-spec record which probably
          # (I'm guessing) has the same meaning as a flagged date.
          values['date'] = handle_event_dates( '' )
          values['flagged'] = True
       else:
          ancestry_note = value.replace( '  ', ' ' )

    for level2 in level1['sub']:
        tag2 = level2['tag']
        value = level2['value']
        if tag2 in ['plac', EVENT_PRIMARY_TAG, EVENT_PROOF_TAG ]:
           values[tag2] = value
        elif tag2 == 'date':
           values[tag2] = handle_event_dates( value )
        elif tag2 == 'note':
           values[tag2] = get_note( level2 )

    if ancestry_note:
       if 'note' in values:
          values['note'] += ' '
       else:
          values['note'] = ''
       values['note'] += ancestry_note

    # If a date didn't show up, for instance knowning only a birth place
    # then even  x['date'] won't exist, so it needs to be checked before
    # the check for x['date']['is_known']
    # For the cases where a date is expected - add the date/not known
    if tag in INDI_EVENT_TAGS + FAM_EVENT_TAGS:
       if 'date' not in values:
          values['date'] = dict()
          values['date']['is_known'] = False

    out_data[tag].append( values )


def handle_custom_event( tag, level1, out_data ):
    """
    Parse an individual or family custom event.
    A value on the tag line becomes added as an item with the key of 'value'.
    GEDCOM spec 7.0.1 pg 65-67
    """

    # A custom event might look like this
    #
    # 1 FACT newspaper
    # 2 TYPE obit
    #
    # or, even though not to spec
    # the event value is in use
    #
    # 1 EVEN 118 cM 2%
    # 2 TYPE dna
    # 2 DATE 1 Aug 2021

    values = dict()
    values['value'] = level1['value']

    for level2 in level1['sub']:
        tag2 = level2['tag']
        value = level2['value']
        if tag2 == 'type':
           values[tag2] = value.lower()
        elif tag2 in [ EVENT_PRIMARY_TAG, EVENT_PROOF_TAG ]:
           values[tag2] = value
        elif tag2 == 'date':
           values[tag2] = handle_event_dates( value )
        elif tag2 == 'note':
           values[tag2] = get_note( level2 )
        else:
           values[tag2] = value

    out_data[tag].append( values )


def extra_name_parts( name, out_data ):
    """ Set additional elements for various uses of the name in HTML, JSON, etc."""

    # It may be more appropriate to use the name translation records (see GEDCOM spec.)
    # but only if those records for text/plain and text/html parts exist. Instead, just
    # do the conversion here.

    out_data['display'] = name

    # There may be unicode/non-UTF-8 chars
    out_data['html'] = convert_to_html( name )
    out_data['unicode'] = convert_to_unicode( name )


def handle_name_tag( tag, level1, out_data ):
    """ Parse the name record. Ensuring a name exists and seconds become alternate names."""

    names = dict()

    # The name cannot be blank on a name tag
    full_name = UNKNOWN_NAME
    if level1['value']:
       full_name = level1['value']
    else:
       print_warn( concat_things( DATA_WARN, 'Blank name replaced with:', full_name ) )

    names['value'] = full_name

    have_surn_parts = False

    for level2 in level1['sub']:
        tag2 = level2['tag']
        # also prevent null values here
        if tag2 in LEVEL2_NAMES:
           value = ''
           if level2['value']:
              value = level2['value']
           if tag2 == 'surn':
              have_surn_parts = True
              if value == '':
                 # special case, surname cannot be empty
                 value = UNKNOWN_NAME
                 print_warn( concat_things( DATA_WARN, 'Blank surname replaced with:', value ) )

           names[tag2] = value

    # Form the display name from the parts (if exist) because they might look better
    value = ''
    if have_surn_parts:
       space = ''
       for tag2 in LEVEL2_NAMES:
           if tag2 in names and tag2 not in LEVEL2_SUB_NAMES:
              value += space + names[tag2]
              space = ' '

    else:
       # or from the saved name without the slashes
       value = full_name.replace( '/', '' )

    extra_name_parts( value, names )

    out_data[tag].append( names )


def ensure_not_twice( tag_list, sect_type, ref_id, data ):
    """ Throw ValueError if an impossible second record is found. """

    for tag in tag_list:
        if tag in data:
           if len(data[tag]) > 1:
              raise ValueError( concat_things( DATA_ERR, sect_type, ref_id, 'tag occured more than once:', tag ) )


def parse_family( level0, out_data ):
    """ Parse a family record from the input section to the parsed families section."""

    # Use this flag on output of modified data
    out_data[PRIVATIZE_FLAG] = PRIVATIZE_OFF

    # Guarantee a child tag exists.The husb and wife might not.
    out_data['chil'] = []

    for level1 in level0['sub']:
        tag = level1['tag']
        value = level1['value']

        # Not everything is copied into the parsed section.
        # Setup an empty list for those things which will be copied.
        parsed = False
        if tag in OTHER_FAM_TAGS + FAM_EVENT_TAGS + FAM_MEMBER_TAGS:
           parsed = True
           if tag not in out_data:
              out_data[tag] = []

        # Now deal with that record.

        if tag in FAM_MEMBER_TAGS:
           out_data[tag].append( extract_indi_id( value ) )

        elif tag in OTHER_FAM_TAGS:
           out_data[tag].append( value )

        elif tag in ['even','fact']:
           # Broken out specially because its custom style must
           # be handled before the below test for general event list.
           handle_custom_event( tag, level1, out_data )

        elif tag in FAM_EVENT_TAGS:
           handle_event_tag( tag, level1, out_data )

        if parsed:
           # Map this file record back to the parsed section just created
           level1['parsed'] = { 'key':tag, 'index': len(out_data[tag])-1 }

    ensure_not_twice( ONCE_FAM_TAGS, 'Family', level0['tag'], out_data )
    set_best_events( FAM_SINGLE_EVENTS, out_data )


def setup_parsed_families( sect, psect, data ):
    """ Parse all families. """
    for i, level0 in enumerate( data[sect] ):
        fam = extract_fam_id( level0['tag'] )
        data[psect][fam] = dict()
        add_file_back_ref( sect, i, data[psect][fam] )

        parse_family( level0, data[psect][fam] )


def parse_individual( level0, out_data ):
    """ Parse an individual record from the input section to the parsed individuals section."""

    # Use this flag on output of modified data
    out_data[PRIVATIZE_FLAG] = PRIVATIZE_OFF

    for level1 in level0['sub']:
        tag = level1['tag']
        value = level1['value']

        # Not everything is copied to the parsed section.
        # Setup an empty list for those things which will be copied.
        parsed = False
        if tag == 'name' or tag in OTHER_INDI_TAGS + INDI_EVENT_TAGS:
           parsed = True
           if tag not in out_data:
              out_data[tag] = []

        # Now deal with that record.

        if tag == 'name':
           handle_name_tag( tag, level1, out_data )

        elif tag in ['fams', 'famc']:
           # These two broken out specially because they use the id extraction
           # must be handled before the test for other-indi-tags.
           out_data[tag].append( extract_fam_id( value ) )

        elif tag in ['even','fact']:
           # This one broken out specially because its a custom event
           # must be handled before the below test for regular events.
           handle_custom_event( tag, level1, out_data )

        elif tag in OTHER_INDI_TAGS:
           out_data[tag].append( value )

        elif tag in INDI_EVENT_TAGS:
           handle_event_tag( tag, level1, out_data )

        if parsed:
           that_index = len(out_data[tag]) - 1
           # Map this file record back to the parsed section just created
           level1['parsed'] = { 'key':tag, 'index':that_index }

    # The name is required
    tag = 'name'
    if tag not in out_data:
       print_warn( concat_things( DATA_WARN, 'Missing name replaced with', UNKNOWN_NAME ) )
       out_data[tag] = []
       names = dict()
       names['value'] = UNKNOWN_NAME
       extra_name_parts( UNKNOWN_NAME, names )
       out_data[tag].append( names )

    ensure_not_twice( ONCE_INDI_TAGS, 'Individual', level0['tag'], out_data )
    set_best_events( INDI_SINGLE_EVENTS, out_data )


def setup_parsed_individuals( sect, psect, data ):
    """ Parse all individuals. """
    for i, level0 in enumerate( data[sect] ):
        indi = extract_indi_id( level0['tag'] )
        data[psect][indi] = dict()
        add_file_back_ref( sect, i, data[psect][indi] )

        parse_individual( level0, data[psect][indi] )


def setup_parsed_sections( data ):
    """ Parse input records into the parsed sections of the data structure."""
    setup_parsed_families( SECT_FAM, PARSED_FAM, data )
    setup_parsed_individuals( SECT_INDI, PARSED_INDI, data )


def check_parsed_sections( data ):
    """ Check xref existance from individuals to families and vise versa."""

    isect = PARSED_INDI
    fsect = PARSED_FAM

    for indi in data[isect]:
        for fam_type in ['fams','famc']:
            if fam_type in data[isect][indi]:
               for fam in data[isect][indi][fam_type]:
                   if fam not in data[fsect]:
                      data[isect][indi][fam_type].remove( fam )
                      message = concat_things( DATA_WARN, SECT_INDI, indi, 'lists', fam, 'in', fam_type, 'but not found.' )
                      if run_settings['exit-on-missing-families']:
                         raise ValueError( message )
                      print_warn( message + ' Removing xref.' )

    for fam in data[fsect]:
        for fam_type in ['husb','wife']:
            if fam_type in data[fsect][fam]:
               for indi in data[fsect][fam][fam_type]:
                   if indi and indi not in data[isect]:
                      data[fsect][fam][fam_type].remove( indi )
                      message = concat_things( DATA_WARN, SECT_FAM, fam, 'lists', fam_type, 'of', indi, 'but not found.' )
                      if run_settings['exit-on-missing-individuals']:
                         raise ValueError( message )
                      print_warn( message + ' Removing xref.' )

        fam_type = 'chil'
        if fam_type in data[fsect][fam]:
           for indi in data[fsect][fam][fam_type]:
               if indi not in data[isect]:
                  data[fsect][fam][fam_type].remove( indi )
                  message = concat_things( DATA_WARN, SECT_FAM, fam, 'lists', fam_type, 'of', indi, 'but not found.' )
                  if run_settings['exit-on-missing-families']:
                     raise ValueError( message )
                  print_warn( message + ' Removing xref.' )


def ensure_int_values( the_list ):
    """ Part of the self consistency checks."""
    message = ''
    if isinstance(the_list,dict):
       comma = ' '
       for key in the_list:
           value = the_list[key]
           if not isinstance(value,int):
              message += comma + str(key) + '/' + str(value)
              comma = ', '
    return message


def ensure_lowercase_values( the_list ):
    """ Part of the self consistency checks."""
    message = ''
    if isinstance(the_list,dict):
       comma = ' '
       for key in the_list:
           value = the_list[key]
           if isinstance(value,str):
              if re.search( r'[A-Z]', value ):
                 message += comma + str(key) + '/' + str(value)
                 comma = ', '
           else:
              message += comma + '+not a string:' + str(key) + '/' + str(value)
              comma = ', '
    return message


def ensure_lowercase_elements( the_list ):
    """ Part of the self consistency checks."""
    message = ''
    if isinstance(the_list,(dict,list)):
       comma = ' '
       for item in the_list:
           if isinstance(item,str):
              if re.search( r'[A-Z]', item ):
                 message += comma + item
                 comma = ', '
           else:
              message += comma + 'not s string:' + str(item)
              comma = ', '
    return message


def ensure_lowercase_constants():
    """ Part of the self consistency checks. Throw ValueError on very bad mistakes."""
    code = SELF_CONSISTENCY_ERR

    # Because tags, dates, etc. are converted to lowercase when parsing.
    message = ''
    message += ensure_lowercase_elements( SECTION_NAMES )
    message += ensure_lowercase_elements( FAM_EVENT_TAGS )
    message += ensure_lowercase_elements( INDI_EVENT_TAGS )
    message += ensure_lowercase_elements( LEVEL2_NAMES )
    message += ensure_lowercase_elements( DATE_MODIFIERS )
    message += ensure_lowercase_elements( MONTH_NUMBERS )
    message += ensure_lowercase_elements( MONTH_NAMES )
    message += ensure_lowercase_elements( CALENDAR_NAMES )
    message += ensure_lowercase_elements( ALT_DATE_MODIFIERS )
    message += ensure_lowercase_elements( OTHER_INDI_TAGS )
    message += ensure_lowercase_elements( FAM_MEMBER_TAGS )
    message += ensure_lowercase_elements( OTHER_FAM_TAGS )
    message += ensure_lowercase_elements( ONCE_INDI_TAGS )
    message += ensure_lowercase_elements( ONCE_FAM_TAGS )
    message += ensure_lowercase_elements( EVENT_PROOF_VALUES )
    message += ensure_lowercase_elements( [ EVENT_PRIMARY_TAG, EVENT_PRIMARY_VALUE, EVENT_PROOF_TAG ] )
    if message:
       raise ValueError( code + 'Uppercase in constant, should be all lower:' + message )

    message = ''
    message += ensure_lowercase_values( ALT_DATE_MODIFIERS )
    if message:
       raise ValueError( code +'Non-string-number' + message )

    message = ''
    message += ensure_int_values( MONTH_NUMBERS )
    message += ensure_int_values( EVENT_PROOF_VALUES )
    if message:
       raise ValueError( code + 'Non-number' + message )

    if len(MONTH_NAMES) != 13:
       raise ValueError( code + 'MONTH_NAMES should have 13 elements' )

    # and mistakes in months
    for key in MONTH_NUMBERS:
        value = MONTH_NUMBERS[key]
        if value < 1 or value > 12:
           raise ValueError( code + 'month number out of range:' + str(key) + '/' + str(value) )

    # the other tags can't be events
    for tag in OTHER_INDI_TAGS:
        if tag in INDI_EVENT_TAGS:
           raise ValueError( code + 'individual tag listed in other and event lists:' + str(tag) )
    for tag in FAM_MEMBER_TAGS + OTHER_FAM_TAGS:
        if tag in FAM_EVENT_TAGS:
           raise ValueError( code + 'family tag listed in other and event lists:' + str(tag) )


def compute_privatize_flag( death_limit, birth_limit, data ):
    """ Use the event dates and date limits to compute a privatization flag setting."""

    # Default to complete privatization for everyone.
    result = PRIVATIZE_MAX

    deceased_keys = ['deat','buri','crem']
    birth_keys = ['birt','bapm','chr']

    tested_date = False

    for key in deceased_keys:
        if key in data:
           if 'date' in data[key][0]:
              if 'flagged' in data[key][0]['date']:
                 # since the person has died, the setting gets relaxed
                 result = PRIVATIZE_MIN
                 break

    # Do the full test again because the burial might be flagged,
    # but the death date might be complete

    for key in deceased_keys:
        if key in data:
           # relax the setting, keep checking the date
           result = PRIVATIZE_MIN
           best_event = data[BEST_EVENT_KEY].get( key, 0 )
           if 'date' in data[key][best_event]:
              if data[key][best_event]['date']['is_known']:
                 tested_date = True
                 # compare with the "max" as the most recent date
                 # less-than means earlier than
                 if data[key][best_event]['date']['max']['value'] <= death_limit:
                    # long ago, don't privatize anything
                    result = PRIVATIZE_OFF
                 break

    if not tested_date:
       # Since a death date wasn't tested,
       # try to use how long ago the person was born.
       #
       # Don't use a "flagged" test - that doesn't tell an age

       for key in birth_keys:
           if key in data:
              best_event = data[BEST_EVENT_KEY].get( key, 0 )
              if 'date' in data[key][best_event]:
                 if data[key][best_event]['date']['is_known']:
                    if data[key][best_event]['date']['max']['value'] <= birth_limit:
                       result = PRIVATIZE_OFF
                    break

    return result


def single_privatize_flag( flag_value, data ):
    """ Set the same privacy flag for everyone. """
    assert isinstance( flag_value, int ), 'Non-int passed as privacy flag'
    assert isinstance( data, dict ), 'Non-dict passed as data'

    for indi in data[PARSED_INDI]:
        data[PARSED_INDI][indi][PRIVATIZE_FLAG] = flag_value

    for fam in data[PARSED_FAM]:
        data[PARSED_FAM][fam][PRIVATIZE_FLAG] = flag_value


def unset_privatize_flag( data ):
    """ Turn off the privatize for everyone."""
    assert isinstance(data,dict), 'Passed data is not a dict'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'
    single_privatize_flag( PRIVATIZE_OFF, data )


def set_privatize_flag( data, years_since_death=20, max_lifetime=104 ):
    """
    Set the privatization for all individuals which is used to hide data via the
    output_priaitized function.

    The default setting for everyone is off.

    Parameters:
       data: the data structure returned from the read_file function

       years_since_death: (default: 20)
               If the person died before this many years: -> off
                      i.e. no hiding events
               If the person died since this many years: -> minimum
                      i.e. show only years rather than exact dates

       max_lifetime: (default 104)
               If a person was born that many years ago, assume they are now deceased.
               The years_since_death test is then applied.

    If a person has no death record and was born less than max_lifetime (or no
    birth record) assume they are still living: -> maximum
          i.e. hide event dates and related sub-structures
               but show events occured with a flagged event such as "1 BIRT Y".

    AssertError will be thrown if the parameters are not integers.
    """

    assert isinstance(data,dict), 'Passed data is not a dict'
    assert isinstance(years_since_death,int), 'years_since_death is not an int'
    assert isinstance(max_lifetime,int), 'max_lifetime is not an int'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'

    # It is possible to guess that ancestors might be deceased based on births of
    # descendants - those calculations are not made, only the known event facts
    # are considered.

    compare_with_death = comparable_before_today( years_since_death )
    compare_with_birth = comparable_before_today( years_since_death + max_lifetime )

    for indi in data[PARSED_INDI]:
        data[PARSED_INDI][indi][PRIVATIZE_FLAG] = compute_privatize_flag( compare_with_death, compare_with_birth, data[PARSED_INDI][indi] )

    # If an individual is flagged, then the families in which they are a parent
    # must also be flagged to the highest level of the parents.

    for fam in data[PARSED_FAM]:
        # Start at off, then find the highest of both partners
        value = PRIVATIZE_OFF
        for partner in [ 'husb', 'wife' ]:
            if partner in data[PARSED_FAM][fam]:
               for indi in data[PARSED_FAM][fam][partner]:
                   value = max( value, data[PARSED_INDI][indi][PRIVATIZE_FLAG] )
        data[PARSED_FAM][fam][PRIVATIZE_FLAG] = value


def read_in_data( inf, data ):
    """
    Read data from the input handle into the data structure.
    At most 5 record levels will be handled.
    Warnings will be printed to std-err for recoverable errors.
    ValueError will be thrown if an unknown file section is detected.
    """

    global version

    # The tag at the most recent level 0 and level 1, etc.
    sect = '?'
    zero = None
    one = None
    two = None
    three = None
    four = None

    # Watch for the last record in the file.
    final_section = '?'

    ignore_line = False
    lines_found = []

    n_line = 0

    for line in inf:
        n_line += 1

        if n_line == 1:
           line = strip_lead_chars( line )

        # GEDCOM pre-7.0, line leading spaces were allowed

        line = line.replace( '\t', ' ' ).strip()

        if line:
           if line.startswith( '0 ' ):
              lc_line = line.lower()
              ignore_line = False

              if lc_line.startswith( '0 head' ):
                 sect = SECT_HEAD

              elif lc_line.startswith( '0 @i' ) and lc_line.endswith( ' indi' ):
                 sect = SECT_INDI
                 if lc_line in lines_found:
                    ignore_line = True
                    print_warn( concat_things( DATA_WARN, 'Duplicate section ignored:', line ) )
                 lines_found.append( lc_line )

              elif lc_line.startswith( '0 @f' ) and lc_line.endswith( ' fam' ):
                 sect = SECT_FAM
                 if lc_line in lines_found:
                    ignore_line = True
                    print_warn( concat_things( DATA_WARN, 'Duplicate section ignored:', line ) )
                 lines_found.append( lc_line )

              elif lc_line.startswith( '0 trlr' ):
                 sect = SECT_TRLR

              elif lc_line.endswith( '@ obje' ):
                 sect = 'obje'

              elif lc_line.endswith( '@ repo' ):
                 sect = 'repo'

              elif lc_line.endswith( '@ sour' ):
                 sect = 'sour'

              elif lc_line.endswith( '@ subm' ):
                 sect = 'subm'

              elif '@ snote' in lc_line:
                 sect = 'snote'

              else:
                 sect = lc_line.replace( '0 ', '', 1 )

              if sect != SECT_HEAD:
                 # Test for version as soon as header is finished
                 if not version:
                    version = confirm_gedcom_version( data )

              if sect not in SECTION_NAMES:
                 message = concat_things( UNK_SECTION_WARN, line )
                 if run_settings['exit-on-unknown-section']:
                    raise ValueError( message )
                 print_warn( message )
                 if sect not in data:
                    data[sect] = []

              if not ignore_line:
                 data[sect].append( line_values( line ) )
                 zero = len( data[sect] ) - 1
                 one = None

              final_section = sect

           elif line.startswith( '1 ' ):
              if not ignore_line:
                 data[sect][zero]['sub'].append( line_values( line ) )
                 one = len( data[sect][zero]['sub'] ) - 1
                 two = None

           elif line.startswith( '2 ' ):
              if not ignore_line:
                 data[sect][zero]['sub'][one]['sub'].append( line_values( line ) )
                 two = len( data[sect][zero]['sub'][one]['sub'] ) - 1
                 three = None

           elif line.startswith( '3 ' ):
              if not ignore_line:
                 data[sect][zero]['sub'][one]['sub'][two]['sub'].append( line_values( line ) )
                 three = len( data[sect][zero]['sub'][one]['sub'][two]['sub'] ) - 1
                 four = None

           elif line.startswith( '4 ' ):
              if not ignore_line:
                 data[sect][zero]['sub'][one]['sub'][two]['sub'][three]['sub'].append( line_values( line ) )
                 four = len( data[sect][zero]['sub'][one]['sub'][two]['sub'][three]['sub'] ) - 1

           elif line.startswith( '5 ' ):
              if not ignore_line:
                 data[sect][zero]['sub'][one]['sub'][two]['sub'][three]['sub'][four]['sub'].append( line_values( line ) )
                 # unlikely to be a level 6

           else:
              print_warn( concat_things( DATA_WARN, 'Level not handled:', line ) )

    if final_section.lower() != SECT_TRLR:
       raise ValueError( concat_things(DATA_ERR,'Final section was not the trailer.' ) )


def read_file( datafile, given_settings=None ):
    """
    Return a dict containing the GEDCOM data in the file.
    Parameter:
       file: name of the data file.

    The calling program should ensure the existance of the file.
    Warnings will be printed to std-err.
    ValueError will be thrown for non-recoverable data errors.

    Settings are optional, see the documentation.
    """
    global run_settings
    global unicode_table

    assert isinstance( datafile, str ), 'Non-string passed as the filename.'

    run_settings = setup_settings( given_settings )

    # The file read into a data structure.
    # See the related document for the format of the dict.
    data = dict()

    # Warn/err messages also goe into the data.
    # Except the self-consistency checks: they are important enough to throw exceptions.
    # Also except the gedcom header and trailer errors.
    # Also file i/o errors which will throw system exceptions.
    data['messages'] = []

    if SELF_CONSISTENCY_CHECKS:
       # Ensure no conflict between the section names.
       for sect in SECTION_NAMES:
           for parsed_sect in [PARSED_INDI, PARSED_FAM]:
               if sect.lower().strip() == parsed_sect.lower().strip():
                  raise ValueError( SELF_CONSISTENCY_ERR + 'section name duplication:' + str(sect) )
       if PARSED_INDI == PARSED_FAM:
          raise ValueError( SELF_CONSISTENCY_ERR + 'section name duplication:' + str(PARSED_INDI) )
       ensure_lowercase_constants()

    unicode_table = setup_unicode_table()

    # These are the zero level tags expected in the file.
    # Some may not occur.
    for sect in SECTION_NAMES:
        data[sect] = []

    # Other sections to be created.
    for sect in [PARSED_INDI, PARSED_FAM]:
        data[sect] = dict()

    with open( datafile, encoding='utf-8' ) as inf:
         read_in_data( inf, data )

    if len( data[SECT_HEAD] ) != 1:
       raise ValueError( DATA_ERR + 'Header must occur once and only once.' )
    if len( data[SECT_TRLR] ) != 1:
       raise ValueError( DATA_ERR + 'Trailer must occur once and only once.' )

    if len( data[SECT_INDI] ) < 1:
       message = concat_things( DATA_WARN, 'No individuals' )
       if run_settings['exit-on-no-individuals']:
          raise ValueError( message )
       print_warn( message )

    if len( data[SECT_FAM] ) < 1:
        message = concat_things( DATA_WARN, 'No families' )
        if run_settings['exit-on-no-families']:
           raise ValueError( message )
        print_warn( message )

    # Since the data has passed the serious tests; form the other portion of the data
    setup_parsed_sections( data )

    # and do some checking
    check_parsed_sections( data )

    # Capture the messages before returning
    data['messages'] = all_messages

    return data


def report_double_facts( data, is_indi, check_list ):
    """ Print events or other records which occur more than once."""
    assert isinstance( check_list, list ), 'Non-list passed as check_list parameter'

    for owner in data.keys():
        name = owner
        if is_indi:
           if 'name' in data[owner]:
              name += ' / ' + data[owner]['name'][0]['display']
        for item in check_list:
            if isinstance( item, str ):
               item = item.lower()
               if item != 'even' and item in data[owner]:
                  n = len( data[owner][item] )
                  if n > 1:
                     print( name, 'has', n, item )


def report_individual_double_facts( data, check_list=None ):
    """
    Print to std-out any individual events which occur more than once.
    Parameters:
       data: the dict returned from the function read_date
       check_list: (default all events) a list of the record types to check.
                   Note that custom events are not tested.

    An assert error is thrown if a non-list is passed.

    Not necessarily used for checking errors but also for getting statistics.
    For instance: find those with alternate names with
        report_individual_double_facts( data, ['name'] )
    Find those with multiple birth type records:
        report_individual_double_facts( data, ['birt','bapm','chr'] )
    """
    assert isinstance( data, dict ), 'Non-dict passed as data'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'

    if check_list is None:
       # this trick is needed for default lists, i.e. defaulted as none
       check_list = INDI_EVENT_TAGS
    report_double_facts( data[PARSED_INDI], True, check_list )


def report_family_double_facts( data, check_list=None ):
    """
    Print to std-out any family events which occur more than once.
    Parameters:
       data: the dict returned from the function read_date
       check_list: (default all events) a list of the record types to check.
                   Note that custom events are not tested.

    An assert error is thrown if a non-list is passed.

    Not necessarily used for checking errors but also for getting statistics.
    For instance: count the number of children for all families
        report_family_double_facts( data, ['chil'] )
    Find families with nultiple engagements:
        report_family_double_facts( data, ['enga'] )
    """
    assert isinstance( data, dict ), 'Non-dict passed as data'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'

    if check_list is None:
       # this trick is needed for default lists, i.e. defaulted as none
       check_list = FAM_EVENT_TAGS
    report_double_facts( data[PARSED_FAM], False, check_list )


def match_individual( indi_data, tag, subtag, search_value, operation ):
    """ Return True if individual's data matches the search condition. """

    def compare( have, want, op ):
        result = False
        if op in ['=','==']:
           result = have == want
        elif op in ['!','!=','not =','not=']:
           result = have != want
        elif op == '<':
           result = have < want
        elif op in ['<=','=<']:
           result = have <= want
        elif op == '>':
           result = have > want
        elif op in ['>=','=>']:
           result = have >= want
        elif op == 'in':
           result = want in have
        elif op in ['!in','not in']:
           result = want not in have
        return result

    def find_best( tag ):
        return indi_data[BEST_EVENT_KEY].get( tag, 0 )


    found = False
    value = None

    if tag == 'name':
       # look in name and alt-names
       for contents in indi_data[tag]:
           if compare( contents['value'], search_value, operation ):
              found = True
              break

    elif tag in ['fams','famc']:
       # look at all the elements
       for value in indi_data[tag]:
           if compare( value, search_value, operation ):
              found = True
              break

    # check the generic event before the standard events
    elif tag in ['even','fact']:
         # an other type of event, maybe a custom fact event
         if subtag:
            # look through all the events for the subtag
            # and check all of that subtype

            if tag in indi_data:
               for event in indi_data[tag]:
                   if event['type'] == subtag:
                      value = event['value']
                      if isinstance( value, str ):
                         found = compare( value, search_value, operation )
                      if found:
                         break

    elif tag in INDI_EVENT_TAGS:
         # its a regular event tag (birth, death, etc.)

         # need to find the best one
         # probably ok to return zero even if its not a single event tag
         # because what does  census.date mean for multi year census entries
         best = find_best( tag )

         # these events have dates and places, if not specified then skip it
         if subtag and subtag in indi_data[tag][best]:
            if subtag == 'date':
               if indi_data[tag][best]['date']['is_known']:
                  value = indi_data[tag][best]['date']['min']['value']
               else:
                  value = indi_data[tag][best][subtag]

         if isinstance( value, str ):
            # be sure to compare a string result against a string as wanted
            found = compare( value, search_value, operation )

    else:
         if tag in indi_data:
            if isinstance( indi_data[tag], list ):
               best = find_best( tag )
               # plain list such as sex, etc.
               value = indi_data[tag][best]
            else:
               # not sure what other item this might be
               value = indi_data[tag]
            if isinstance( value, str ):
               found = compare( value, search_value, operation )

    return found


def get_indi_display( indi_data ):
    """ Return a dict of basic details for an individual. """

    def get_indi_date( indi_data, tag ):
        """ Return the best input file date for the given tag, or the empty string.
            Two date items are returned:  [modifier] dd mmm yyyy  and  [modifier] year """
        def cleanup( s ):
            return s.upper().replace( '  ', ' ' ).strip()

        full_result = ''
        year_result = ''
        best = indi_data[BEST_EVENT_KEY].get( tag, 0 )
        if tag in indi_data:
           if 'date' in indi_data[tag][best]:
              if indi_data[tag][best]['date']['is_known']:
                 modifier = indi_data[tag][best]['date']['min']['modifier']
                 value = indi_data[tag][best]['date']['min']['value']
                 full_result = modifier + ' ' + yyyymmdd_to_date( value )
                 year_result = modifier + ' ' + value[0:4]
                 if indi_data[tag][best]['date']['is_range']:
                    modifier = indi_data[tag][best]['date']['max']['modifier']
                    value = indi_data[tag][best]['date']['max']['value']
                    full_result += ' ' + modifier + ' ' + yyyymmdd_to_date( value )
        return [ cleanup(full_result), cleanup(year_result) ]

    result = dict()

    result['name'] = indi_data['name'][0]['display']
    result['unicode'] = indi_data['name'][0]['unicode']
    result['html'] = indi_data['name'][0]['html']

    date_result = get_indi_date( indi_data, 'birt' )
    result['birt'] = date_result[0]
    result['birt.year'] = date_result[1]

    date_result = get_indi_date( indi_data, 'deat' )
    result['deat'] = date_result[0]
    result['deat.year'] = date_result[1]

    return result


def print_individuals( data, id_list ):
    """
    Print to stdout the vital details for the people in the id list,
    such as returned by the finf function.
    """

    assert isinstance( id_list, list ), 'Non-list passed as id_list'
    assert isinstance( data, dict ), 'Non-dict passed as data'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'

    # header
    print( 'id\tName\tBirth\tDeath' )

    for indi in id_list:
        if isinstance( indi, str ):
           if indi in data[PARSED_INDI]:
              info = get_indi_display( data[PARSED_INDI][indi] )
              print( indi + '\t' + info['name'] + '\t' + info['birt'] + '\t' + info['deat'] )


def find_individuals( data, search_tag, search_value, operation='=' ):
    """
    Return a list of ids of the individual which match the search conditions.
    Parameters:
        data: as returned from read_file
        search_tag: tag such as "name", "fams", "exid", etc.
                    For events the sub-tags may be specified such as
                    "birt.date", "deat.plac", etc.
                    Also, items which are custom facts which are events
                    must be specified like this  "event.exid" or "even.exid"
        search_value: for matching against the data. Must be a string.
                    For dates specify as "yyyymmdd".
        operation: (default "=") matching condition, one of
                    "=", "!=", ">", ">=", "<", "<=", "in", "not in", "exist", "not exist".

    In the case of date ranges, the minimum date is used.
    In the case of multiple events, the "best" event instance is used.
    """

    def existance_match( individual, tag, subtag ):
        result = False

        if tag in individual:

           if tag == 'even':
              # scan through all the custom events
              for event in individual[tag]:
                  if 'type' in event and event['type'] == subtag:
                     result = True
                     break

           else:
              best = 0
              if BEST_EVENT_KEY in individual:
                 if tag in individual[BEST_EVENT_KEY]:
                    best = individual[BEST_EVENT_KEY][tag]

              if subtag:
                 result = subtag in individual[tag][best]
              else:
                 # no test for subtag, the tag exists
                 result = True

        return result


    OPERATORS = ['=', '!=', '<', '<=', '>', '=>', 'in', 'not in', 'exist', 'not exist']
    ALT_OPERATORS = {'==':'=', 'not=':'!=', 'not =':'!=', '=<':'<=', '>=':'=>', '!in':'not in', 'exists':'exist', 'not exists':'not exist', '!exist':'not exist', '!exists':'not exist' }

    # full words
    ALT_TAG = {'birth':'birt', 'born':'birt', 'death':'deat', 'died':'deat', 'event':'even' }
    ALT_SUBTAG = { 'place':'plac' }

    # possibly handle marriage lookups in a future version
    #ALT_SUBTAG = {'marriage':'marr', 'divorce':'div' }

    # Use this to skip an event defaulting the the date subtag
    # for example when checking existance of any birth tag rather than just birth.date
    IGNORE_SUBTAG_VALUE = '_'

    assert isinstance( data, dict ), 'Non-dict passed as data'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'
    assert isinstance(search_tag,str), 'Non-string passed as search_tag'
    assert isinstance(search_value,str), 'Non-string passed as search_value'
    assert isinstance(operation,str), 'Non-string passed as comparison operator'
    assert operation.lower().strip() in OPERATORS or operation.lower().strip() in ALT_OPERATORS, 'Invalid comparison operator:' + operation + ' not one of ' + str(OPERATORS)
    assert search_tag.strip() != '', 'Passed an empty search tag'

    search_tag = search_tag.lower().strip()
    operation = operation.lower().strip()

    # The selection tag might be a sub-section,
    # such as a date or birth: passed as birt.date
    # or place of death passed as deat.plac

    search_subtag = None
    if '.' in search_tag:
       parts = search_tag.split( '.', 1 )
       if parts[0]:
          search_tag = parts[0]
       else:
          raise ValueError( 'Empty search tag start part.' )
       if parts[1]:
          search_subtag = parts[1]
          if search_subtag in ALT_SUBTAG:
             search_subtag = ALT_SUBTAG[search_subtag]
       else:
          raise ValueError( 'Empty search sub-tag.' )

    if search_tag in ALT_TAG:
       search_tag = ALT_TAG[search_tag]

    # Default to date
    if not search_subtag:
       if search_tag in INDI_EVENT_TAGS:
          search_subtag = 'date'
       # but, check for the ignore value after the default is set
       if search_subtag == IGNORE_SUBTAG_VALUE:
          search_subtag = None

    if search_subtag in ALT_SUBTAG:
       search_tag = ALT_SUBTAG[search_subtag]

    if operation in ALT_OPERATORS:
       operation = ALT_OPERATORS[operation]

    result = []

    if operation == 'exist':
       for indi in data[PARSED_INDI]:
           if existance_match( data[PARSED_INDI][indi], search_tag, search_subtag ):
              result.append( indi )

    elif operation == 'not exist':
       for indi in data[PARSED_INDI]:
           if not existance_match( data[PARSED_INDI][indi], search_tag, search_subtag ):
              result.append( indi )

    else:
       for indi in data[PARSED_INDI]:
           if search_tag in data[PARSED_INDI][indi]:
              if match_individual( data[PARSED_INDI][indi], search_tag, search_subtag, search_value, operation ):
                 result.append( indi )

    return result


def get_indi_descendant_count( indi, individuals, families, counts ):
    n_desc = 0
    n_child = 0
    n_gen = 0
    if 'fams' in individuals[indi]:
       for fam in individuals[indi]['fams']:
           for child in families[fam]['chil']:
               # one more child for this person
               n_child += 1
               if child not in counts:
                  counts[child] = get_indi_descendant_count( child, individuals, families, counts )
               # this child plus the child's descendants
               n_desc += 1 + counts[child][1]
               # largest generations of all the children
               n_gen = max( n_gen, counts[child][2] )
    if n_child > 0:
       # count the children's generation
       n_gen += 1
    return ( n_child, n_desc, n_gen )


def print_descendant_count( indi, indi_data, indi_counts, header=False ):
    """ Print a single count line. """

    if header:
       print( 'id\tName\tBirth\tDeath\tChildren\tDescendants\tGenerations' )
    else:
       results = get_indi_display( indi_data )
       out = indi
       out += '\t' + results['name']
       out += '\t' + results['birt']
       out += '\t' + results['deat']
       out += '\t' + str( indi_counts[0] )
       out += '\t' + str( indi_counts[1] )
       out += '\t' + str( indi_counts[2] )
       print( out )


def report_indi_descendant_count( indi, data ):
    """
    Print to stdout a tab delimited file of this person's descendant count.
    """
    assert isinstance( data, dict ), 'Non-dict passed as data'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'
    assert isinstance( indi, str ), 'Non-string given as the individual id'

    print_descendant_count( None, None, None, header=True )

    if indi in data[PARSED_INDI]:
       counts = dict()
       indi_counts = get_indi_descendant_count( indi, data[PARSED_INDI], data[PARSED_FAM], counts )
       print_descendant_count( indi, data[PARSED_INDI][indi], indi_counts )


def report_all_descendant_count( data ):
    """
    Print to stdout a tab delimited file of everyone and their descendant count.
    """
    assert isinstance( data, dict ), 'Non-dict passed as data'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'

    counts = dict()

    for indi in data[PARSED_INDI]:
        if indi not in counts:
           counts[indi] = get_indi_descendant_count( indi, data[PARSED_INDI], data[PARSED_FAM], counts )

    print_descendant_count( None, None, None, header=True )

    for indi in counts:
        print_descendant_count( indi, data[PARSED_INDI][indi], counts[indi] )
