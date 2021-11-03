"""
Read a GEDCOM file into a data structure, parse into a dict of
individuals and families for simplified handling; converting to
HTML pages, JSON data, etc.

Public functions:
    data = read_file( gedcom_file_name )

    output_original( data, out_file_name )

    set_privatize_flag( data )

    unset_privatize_flag( data )

    output_privatized( data, out_file_name )

    report_individual_double_facts( data )

    report_family_double_facts( data )

    report_descendant_report( data )

    id_list = find_individuals( data, search_tag, search_value, operation='=' )

    print_individuals( data, id_list )

    output_indi_ancestor_dot( data, indi [,output_file] )

    output_all_dot( data [,output_file] )

    output_all_json( data [,output_file] )


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
Copyright (c) 2021 John A. Andrea
v1.2
"""

import sys
import json
import copy
import re
import datetime

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
INDI_EVENT_TAGS = ['bapm','barm','basm','bles','buri','cens','chra','conf','crem','deat','emig','fcom','grad','immi','natu','ordn','prob','reti','will','adop','birt','chr','even']

# Other individual tags of interest placed into the parsed section,
# in addition to the event tags and of course the name(s)
OTHER_INDI_TAGS = ['sex', 'exid', 'fams', 'famc']

# Other family tag of interest placed into the parsed section,
# in addition to the event tags
FAM_MEMBER_TAGS = ['husb', 'wife', 'chil']
OTHER_FAM_TAGS = []

# Individual records which are only allowed to occur once.
# However they will still be placed into an array to be consistent
# with the other facts/events.
# An exception will be thrown if a duplicate is found.
# Use of a validator is recommended.
ONCE_INDI_TAGS = ['sex', 'exid']

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

# Name sub-parts in order of display appearance
LEVEL2_NAMES = ['npfx', 'givn', 'surn', 'nsfx']

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
CRASH_ON_BAD_DATE = False
DATE_ERR = 'Malformed date:'

# The message for data file troubles
DATA_ERR = 'GEDCOM error. Use a validator. '
DATA_WARN = 'Warning. Use a validator. '

# What to do with unknown sections
CRASH_ON_UNK_SECTION = False
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
SELF_CONSISTENCY_CHECKS = True
SELF_CONSISTENCY_ERR = 'Program code inconsistency:'

# The detected version of the input file.
version = ''


def convert_to_unicode( text ):
    """ Convert common utf-8 encoded characters to unicode for the various display of names etc."""
    text = text.replace( '\xe7', '\\u00e7' ) #c cedilia
    text = text.replace( '\xe9', '\\u00e9' ) #e acute
    text = text.replace( '\xc9', '\\u00c9' ) #E acute
    text = text.replace( '\xe8', '\\u00e8' ) #e agrave
    text = text.replace( '\xe1', '\\u00e1' ) #a acute
    text = text.replace( '\xc1', '\\u00c1' ) #A acute
    text = text.replace( '\xe0', '\\u00e0' ) #a agrave
    text = text.replace( '\xf6', '\\u00f6' ) #o diaresis
    return text


def convert_to_html( text ):
    """ Convert common utf-8 encoded characters to html for the various display of names etc."""
    text = text.replace( '<', '&lt;' )
    text = text.replace( '>', '&gt;' )
    text = text.replace( '\xe7', '&#231;' ) #c cedilia
    text = text.replace( '\xe9', '&#233;' ) #e acute
    text = text.replace( '\xc9', '&#201;' ) #E acute
    text = text.replace( '\xe8', '&#232;' ) #e agrave
    text = text.replace( '\xe1', '&#225;' ) #a acute
    text = text.replace( '\xc1', '&#193;' ) #A acute
    text = text.replace( '\xe0', '&#224;' ) #a agrave
    text = text.replace( '\xf6', '&#246;' ) #o diaresis
    return text


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
    """ Copy a portion of the data frmo one section to another."""
    if from_sect in SECTION_NAMES:
       if from_sect in data:
          data[to_sect] = copy.deepcopy( data[from_sect] )
       else:
          data[to_sect] = []
    else:
       print( 'Cant copy unknown section:', from_sect, file=sys.stderr )


#def copy_header( data ):
#    # Example
#    copy_section( SECT_HEAD, 'header', data )


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
    Returns a tuple:
       ( 'yyyymmdd', malformed )

    where "malformed" is True if the original had to be repaired to be usable.

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
    # 'nov 1996' returns '19961101'
    # '1996' returns '19960101'
    # '' returns ''
    # 'seven nov 1996' returns '19961101' or throws ValueError
    # '7 never 1996' returns '19960107' or throws ValueError
    # '7 nov ninesix' returns '00011107' or throws ValueError

    default_day = 1
    default_month = 1
    default_year = 1

    result = None
    malformed = False

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

       elif len( parts ) == 2:
          month = parts[0]
          year = parts[1]

       elif len( parts ) == 3:
          day = parts[0]
          month = parts[1]
          year = parts[2]

       else:
          if CRASH_ON_BAD_DATE:
             raise ValueError( DATE_ERR + ':' + str(original) )
          malformed = True
          print( DATE_ERR, original, ': setting to', year, month, day, file=sys.stderr )

       if isinstance(day,str):
          #i.e. has been extracted from the given date string
          if string_like_int( day ):
             day = int( day )
             if day < 1 or day > 31:
                day = default_day
                if CRASH_ON_BAD_DATE:
                   raise ValueError( DATE_ERR + ':' + str(original) )
                malformed = True
                print( DATE_ERR, original, ': setting day to', day, file=sys.stderr )
          else:
             if CRASH_ON_BAD_DATE:
                raise ValueError( DATE_ERR + ':' + str(original) )
             day = default_day
             malformed = True
             print( DATE_ERR, original, ': setting day to', day, file=sys.stderr )

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
                if CRASH_ON_BAD_DATE:
                   raise ValueError( DATE_ERR + ':' + str(original) )
                month = default_month
                print( DATE_ERR, original, ': setting month to number', month, file=sys.stderr )

       if isinstance(year,str):
          #i.e. has been extracted from the given date string
          if string_like_int( year ):
             year = int( year )
          else:
             malformed = True
             print( DATE_ERR, original, ': attempting to correct', file=sys.stderr )
             # Ancestry mistakes
             year = year.replace( '-', '' ).replace( '.', '' )
             if string_like_int( year ):
                year = int( year )
             else:
                if CRASH_ON_BAD_DATE:
                   raise ValueError( DATE_ERR + ':' + str(original) )
                year = default_year
                print( DATE_ERR, original, ': setting year to:', year, file=sys.stderr )

       result = '%04d%02d%02d' % ( year, month, day )

    return ( result, malformed )


def date_comparable_results( original, key, date_data ):
    """ Get the results from the to-comparable conversion and set into the date data values."""
    results = date_to_comparable( original )

    date_data[key]['value'] = results[0]

    # Set true if false
    if not date_data['malformed']:
       date_data['malformed'] = results[1]


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


def set_best_events( event_list, always_first_list, out_data ):
    """ For each event with multiple instances within a single individual or family
        Set the index of the "best" instance based on the proof and primary settings."""

    # Note that custom event records with the tag "even" are not included
    # because of the the associated even.type

    out_data[BEST_EVENT_KEY] = dict()

    # Best name is always the first one, and it must exist
    out_data[BEST_EVENT_KEY]['name'] = 0

    # No further tests for the "best" of these ones. Always set to index zero.
    # Set for consistency with all events.
    for tag in always_first_list:
        if tag in out_data:
           out_data[BEST_EVENT_KEY][tag] = 0


    # Initial value is smaller than the smallest of all in order for the first test
    # to pick up the first item tested.
    smallest = min( EVENT_PROOF_VALUES.values() ) - 1

    for tag in event_list:
        if tag != 'even':
           if tag in out_data:
              found_best = 0
              if len( out_data[tag] ) > 1:
                 # If there is a disproven marked as primary - choose any other.

                 # Find the best: disproven having lowest value, proven is highest
                 value_best = smallest
                 for i, section in enumerate( out_data[tag] ):
                     value = EVENT_PROOF_VALUES[EVENT_PROOF_DEFAULT]
                     if EVENT_PROOF_TAG in section:
                        proof_setting = section[EVENT_PROOF_TAG].lower()
                        if proof_setting in EVENT_PROOF_VALUES:
                           value = EVENT_PROOF_VALUES[proof_setting]
                     # just the existance of this tag is good enough
                     if EVENT_PRIMARY_TAG in section:
                        # even better
                        value *= 10
                     if value > value_best:
                        value_best = value
                        found_best = i

              out_data[BEST_EVENT_KEY][tag] = found_best


def handle_event_dates( value ):
    """ Parse a event date. Special cases could be handled in here."""
    return date_to_structure( value )


def handle_event_tag( tag, level1, out_data ):
    """ Parse an individual or family event record."""

    # An event record look like this
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

    out_data[tag].append( values )


def handle_custom_event( tag, level1, out_data ):
    """ Parse an individual or family custom event."""

    # A custom event might look like this
    #
    #1 EVEN 118 cM 2%
    #2 TYPE dna
    #2 DATE 1 Aug 2021

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
       print( DATA_WARN, 'Blank name replaced with:', full_name, file=sys.stderr )

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
                 print( DATA_WARN, 'Blank surname replaced with:', value, file=sys.stderr )

           names[tag2] = value

    # Form the display name from the parts (if exist) because they might look better
    value = ''
    if have_surn_parts:
       space = ''
       for tag2 in LEVEL2_NAMES:
           if tag2 in names:
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
              raise ValueError( DATA_ERR + sect_type + ' ' + ref_id + ' tag occured more than once:' + str(tag) )


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

        elif tag == 'even':
           # Broken out specially because its custom style must
           # be handled before the below test for general event list.
           handle_custom_event( tag, level1, out_data )

        elif tag in FAM_EVENT_TAGS:
           handle_event_tag( tag, level1, out_data )

        if parsed:
           # Map this file record back to the parsed section just created
           level1['parsed'] = { 'key':tag, 'index': len(out_data[tag])-1 }

    ensure_not_twice( ONCE_FAM_TAGS, 'Family', level0['tag'], out_data )
    set_best_events( FAM_EVENT_TAGS, ONCE_FAM_TAGS, out_data )


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

        elif tag in OTHER_INDI_TAGS:
           out_data[tag].append( value )

        elif tag == 'even':
           # This one broken out specially because its a custom event
           # must be handled before the below test for regular events.
           handle_custom_event( tag, level1, out_data )

        elif tag in INDI_EVENT_TAGS:
           handle_event_tag( tag, level1, out_data )

        if parsed:
           that_index = len(out_data[tag]) - 1
           # Map this file record back to the parsed section just created
           level1['parsed'] = { 'key':tag, 'index':that_index }

    # The name is required
    tag = 'name'
    if tag not in out_data:
       print( DATA_WARN, 'Missing name replaced with', UNKNOWN_NAME, file=sys.stderr )
       out_data[tag] = []
       names = dict()
       names['value'] = UNKNOWN_NAME
       extra_name_parts( UNKNOWN_NAME, names )
       out_data[tag].append( names )

    ensure_not_twice( ONCE_INDI_TAGS, 'Individual', level0['tag'], out_data )
    set_best_events( INDI_EVENT_TAGS, ONCE_INDI_TAGS, out_data )


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
                   if not fam in data[fsect]:
                      print( SECT_INDI, indi, 'lists', fam, 'in', fam_type, 'but not found. Removing xref.', file=sys.stderr )
                      data[isect][indi][fam_type].remove( fam )

    for fam in data[fsect]:
        for fam_type in ['husb','wife']:
            if fam_type in data[fsect][fam]:
               for indi in data[fsect][fam][fam_type]:
                   if indi and indi not in data[isect]:
                      print( SECT_FAM, fam, 'lists', fam_type, 'of', indi, 'but not found. Removing xref.', file=sys.stderr )
                      data[fsect][fam][fam_type].remove( indi )
        fam_type = 'chil'
        if fam_type in data[fsect][fam]:
           for indi in data[fsect][fam][fam_type]:
               if indi not in data[isect]:
                  print( SECT_FAM, fam, 'lists', fam_type, 'of', indi, 'but not found. Removing xref.', file=sys.stderr )
                  data[fsect][fam][fam_type].remove( indi )


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
           best_event = data[BEST_EVENT_KEY][key]
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
              best_event = data[BEST_EVENT_KEY][key]
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
                    print( DATA_WARN, 'Duplicate section ignored:', line, file=sys.stderr )
                 lines_found.append( lc_line )

              elif lc_line.startswith( '0 @f' ) and lc_line.endswith( ' fam' ):
                 sect = SECT_FAM
                 if lc_line in lines_found:
                    ignore_line = True
                    print( DATA_WARN, 'Duplicate section ignored:', line, file=sys.stderr )
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
                 if CRASH_ON_UNK_SECTION:
                    raise ValueError( UNK_SECTION_ERR + str(line) )
                 print( UNK_SECTION_WARN, line, file=sys.stderr )
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
              print( DATA_WARN + 'Level not handled:', line, file=sys.stderr )

    if final_section.lower() != SECT_TRLR:
       raise ValueError( DATA_ERR + 'Final section was not the trailer.' )


def read_file( datafile ):
    """
    Return a dict containing the GEDCOM data in the file.
    Parameter:
       file: name of the data file.

    The calling program should ensure the existance of the file.
    Warnings will be printed to std-err.
    ValueError will be thrown for non-recoverable data errors.
    """
    assert isinstance( datafile, str ), 'Non-string passed as the filename.'

    # See the related document for the format of the dict.

    if SELF_CONSISTENCY_CHECKS:
       # Ensure no conflict between the section names.
       for sect in SECTION_NAMES:
           for parsed_sect in [PARSED_INDI, PARSED_FAM]:
               if sect.lower().strip() == parsed_sect.lower().strip():
                  raise ValueError( SELF_CONSISTENCY_ERR + 'section name duplication:' + str(sect) )
       if PARSED_INDI == PARSED_FAM:
          raise ValueError( SELF_CONSISTENCY_ERR + 'section name duplication:' + str(PARSED_INDI) )
       ensure_lowercase_constants()

    # The file read into a data structure.
    data = dict()

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
       raise ValueError( DATA_ERR + 'No individuals.' )
    if len( data[SECT_FAM] ) < 1:
       # This is not a fatal problem, only a warning
       print( DATA_WARN, 'No families.', file=sys.stderr )

    # Since the data has passed the serious tests; form the other portion of the data
    setup_parsed_sections( data )

    # and do some checking
    check_parsed_sections( data )

    return data


def report_double_facts( data, is_indi, check_list ):
    """ Print events or other records occur more than once."""
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
    """ Return True if individual's data matches the search condition."""

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

    found = False

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

    elif isinstance( indi_data[tag], list ):
       # its a list, determine the best one
       best = 0
       if BEST_EVENT_KEY in indi_data:
          if tag in indi_data[BEST_EVENT_KEY]:
             best = indi_data[BEST_EVENT_KEY][tag]

       if tag in INDI_EVENT_TAGS:
          # events have dates and places, if not specified then skip it
          if subtag:
             if subtag in indi_data[tag][best]:
                if subtag == 'date':
                   if indi_data[tag][best]['date']['is_known']:
                      value = indi_data[tag][best]['date']['min']['value']
                   else:
                      value = indi_data[tag][best][subtag]
       else:
         # plain list such as sex,exid, etc. not an event
         value = indi_data[tag][best]

       if isinstance(value,str):
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
        best = 0
        if BEST_EVENT_KEY in indi_data:
           if tag in indi_data[BEST_EVENT_KEY]:
              best = indi_data[BEST_EVENT_KEY][tag]
        if tag in indi_data:
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
        search_value: for matching against the data. Must be a string.
                    For dates specify as "yyyymmdd".
        operation: (default "=") matching condition, one of
                    "=", "!=", ">", ">=", "<", "<=", "in", "not in".

    In the case of date ranges, the minimum date is used.
    In the case of multiple events, the "best" event instance is used.
    Custom events never matched (in this version).
    """

    OPERATORS = ['=','==','!','!=','not =', 'not=', '<','<=','=<','>','>=','=>','in','!in','not in']

    assert isinstance( data, dict ), 'Non-dict passed as data'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'
    assert isinstance(search_tag,str), 'Non-string passed as search_tag'
    assert isinstance(search_value,str), 'Non-string passed as search_key'
    assert isinstance(operation,str), 'Non-string passed as comparison operator'
    assert operation.lower().strip() in OPERATORS, 'Invalid comparison operator:' + operation + ' not one of ' + str(OPERATORS)
    assert search_tag.strip() != '', 'Passed an empty search tag'

    search_tag = search_tag.lower().strip()
    operation = operation.lower().strip()

    # The selection tag might be a sub-section,
    # such as a date or birth: passed as birt.date
    # or place of death passed as deat.plac

    search_subtag = None
    if '.' in search_tag:
       parts = search_tag.split('.')
       if parts[0]:
          search_tag = parts[0]
       else:
          raise ValueError( 'Empty search tag start part.' )
       if parts[1]:
          search_subtag = parts[1]
       else:
          raise ValueError( 'Empty search sub-tag.' )

    result = []

    if search_tag != 'even':
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


def out_file_all_dot( data, fh ):
    def get_info( indi_data ):
        info = get_indi_display( indi_data )
        return info['html']
    def draw_link( indi_link, parents_tag, fh ):
        # the middle of the parent record
        parents_link = parents_tag + ':p'
        print( indi_link + ' -> ' + parents_link + ';', file=fh )
    def make_fam_tag( fam ):
        # to identify the record in the dot output
        return 'f_' + str( fam )
    def make_indi_tag( indi ):
        # to identify the record in the dot output
        return 'i_' + str( indi )
    def output_parent_pairs( individuals, families, fh ):
        for fam in families:
            names = dict()
            for partner in ['husb','wife']:
                names[partner] = UNKNOWN_NAME
                if partner in families[fam]:
                   indi = families[fam][partner][0]
                   names[partner] = get_info( individuals[indi] )

            # label ids are h=husb, w=wife => first character of the word
            out = make_fam_tag( fam ) + ' [label="'
            out += '<h>' + names['husb']
            out += '|<p>|'  # middle area, potentially marriage date could go in here
            out += '<w>' + names['wife']
            out += '"];'
            print( out, file=fh )

    def link_parents_to_grand( individuals, families, fh ):
        for fam in families:
            for partner in ['husb','wife']:
                if partner in families[fam]:
                   indi = families[fam][partner][0]
                   if 'famc' in individuals[indi] and individuals[indi]['famc'][0]:
                      parents_fam = individuals[indi]['famc'][0]
                      parents_tag = make_fam_tag( parents_fam )
                      # get the h or w part of this marriage record
                      partner_link = make_fam_tag( fam ) + ':' + partner[0]
                      draw_link( partner_link, parents_tag, fh )

    def link_single_to_parents( individuals, fh ):
        for indi in individuals:
            if 'fams' not in individuals[indi]:
               if 'famc' in individuals[indi] and individuals[indi]['famc'][0]:
                  indi_tag = make_indi_tag( indi )
                  info = get_info( individuals[indi] )
                  parents_tag = make_fam_tag( individuals[indi]['famc'][0] )
                  print( indi_tag + ' [label="<i> ' + info + '"];', file=fh )
                  draw_link( indi_tag + ':i', parents_tag, fh )

    print( 'digraph family {', file=fh )
    print( 'node [shape=record];', file=fh )
    print( 'rankdir=LR;', file=fh )

    # output all the marriage/partnership records
    output_parent_pairs( data[PARSED_INDI], data[PARSED_FAM], fh )

    # connect each member of a marriage to their parents
    link_parents_to_grand( data[PARSED_INDI], data[PARSED_FAM], fh )

    # everyone else
    link_single_to_parents( data[PARSED_INDI], fh )

    # done
    print( '}', file=fh )


def out_file_indi_ancestor_dot( data, indi, fh ):
    def get_info( indi_data ):
        # potentially check for privitization
        info = get_indi_display( indi_data )
        result = info['html']
        dates = info['birt.year'] + ' - ' + info['deat.year']
        dates = dates.strip()
        if dates and dates != '-':
           # not a newline, but the string that will become a newline
           result += '\\n' + dates
        return result
    def make_fam_tag( fam ):
        # to identify the record in the dot output
        return 'f_' + str(fam)
    def make_indi_tag( indi ):
        # to identify the record in the dot output
        return 'i_' + str(indi)
    def link_parents( individuals, families, fam, indi_link, fh ):
        names = dict()
        for partner in ['husb','wife']:
            names[partner] = UNKNOWN_NAME
            if partner in families[fam]:
               indi = families[fam][partner][0]
               names[partner] = get_info( individuals[indi] )

        fam_tag = make_fam_tag( fam )

        # draw the box for the parents
        out = fam_tag + ' [label="'
        out += '<h>' + names['husb']
        out += '|<p>|'  # potentially marriage date could go in here
        out += '<w>' + names['wife']
        out += '"];'
        print( out, file=fh )

        # connect the child
        parents_link = fam_tag + ':p'
        print( indi_link + ' -> ' + parents_link + ';', file=fh )

        # follow the parents
        for partner in ['husb','wife']:
            if partner in families[fam]:
               partner_id = families[fam][partner][0]
               if 'famc' in individuals[partner_id] and individuals[partner_id]['famc'][0]:
                  grandparent_fam = individuals[partner_id]['famc'][0]
                  partner_link = fam_tag + ':' + partner[0]
                  link_parents( individuals, families, grandparent_fam, partner_link, fh )

    print( 'digraph family {', file=fh )
    print( 'node [shape=record];', file=fh )
    print( 'rankdir=LR;', file=fh )

    # the individual
    info = get_info( data[PARSED_INDI][indi] )
    indi_tag = make_indi_tag( indi )
    print( indi_tag + '[label="<i> ' + info + '"];', file=fh )

    if 'famc' in data[PARSED_INDI][indi] and data[PARSED_INDI][indi]['famc'][0]:
       indi_link = indi_tag + ':i'
       parents_fam = data[PARSED_INDI][indi]['famc'][0]
       link_parents( data[PARSED_INDI], data[PARSED_FAM], parents_fam, indi_link, fh )

    # done
    print( '}', file=fh )


def output_indi_ancestor_dot( data, indi, out_name=None ):
    """
    Print a Graphviz dot file representation of the ancetors or the given individual.
    If the third parameter exists: output to that filename, else output to stdout.
    """
    assert isinstance( data, dict ), 'Non-dict passed as data'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'

    plain_file = False

    fh = sys.stdout
    if out_name and out_name != '-':
       plain_file = True
       fh = open( out_name, 'w' )

    if indi in data[PARSED_INDI]:
       out_file_indi_ancestor_dot( data, indi, fh )

    if plain_file:
       fh.close()


def output_all_dot( data, out_name=None ):
    """
    Print a Graphviz dot file representation of all the families in the data.
    If the second parameter exists: output to that filename, else output to stdout.
    """
    assert isinstance( data, dict ), 'Non-dict passed as data'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'

    plain_file = False

    fh = sys.stdout
    if out_name and out_name != '-':
       plain_file = True
       fh = open( out_name, 'w' )

    out_file_all_dot( data, fh )

    if plain_file:
       fh.close()


def output_all_json( data, out_name=None ):
    """
    Print a JSON file representation of the descendants of everyone.
    If the second parameter exists: output to that filename, else output to stdout.
    """
    assert isinstance( data, dict ), 'Non-dict passed as data'
    assert PARSED_INDI in data, 'Passed data appears to not be from read_file'

    def drop_lead( identifier ):
        return str(identifier).replace( 'i', '' ).replace( 'f', '' )

    def add_individuals( individuals ):
        def add_individual( indi_data, name_parts ):
            result = dict()
            for item in ['fams','famc']:
                if item in indi_data:
                   result[item] = []
                   for fam in indi_data[item]:
                       result[item].append( drop_lead( fam ) )
            item = 'sex'
            if item in indi_data:
               result[item] = indi_data[item][0]

            info = get_indi_display( indi_data )
            result['name'] = info['unicode']
            if info['birt']:
               result['birth'] = info['birt']
            if info['deat']:
               result['death'] = info['deat']

            for item in name_parts:
                if item in indi_data and indi_data[item]:
                   result[name_parts[item]] = convert_to_unicode( indi_data[item] )

            return result

        # match additional parts
        name_parts = dict()
        name_parts['givn'] = 'given'
        name_parts['surn'] = 'surname'
        name_parts['nick'] = 'nickname'

        result = dict()
        for indi in individuals:
            result[drop_lead(indi)] = add_individual( individuals[indi], name_parts )
        return result

    def add_families( families ):
        def add_family( fam_data ):
            result = dict()
            result['husband'] = None
            result['wife'] = None
            result['children'] = []
            if 'husb' in fam_data:
               result['husband'] = drop_lead( fam_data['husb'][0] )
            if 'wife' in fam_data:
               result['wife'] = drop_lead( fam_data['wife'][0] )
            if 'chil' in fam_data:
               for child in fam_data['chil']:
                   result['children'].append( drop_lead( child ) )
            return result

        result = dict()
        for fam in families:
            result[drop_lead(fam)] = add_family( families[fam] )
        return result

    plain_file = False

    fh = sys.stdout
    if out_name and out_name != '-':
       plain_file = True
       fh = open( out_name, 'w' )

    result = dict()
    result['individuals'] = add_individuals( data[PARSED_INDI] )
    result['families'] = add_families( data[PARSED_FAM] )

    json.dump( result, fh, indent=2 )

    if plain_file:
       fh.close()
