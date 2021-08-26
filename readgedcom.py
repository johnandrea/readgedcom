# Parse a gedcom file into a data structure.
#
# The input file should be well formed as this code only checks for
# a few structural errors. A verification program can be found here:
# https://chronoplexsoftware.com/gedcomvalidator/
#   Fixable mistakes are corrected as the data is parsed into the data structure.
# If the option to output a privatized file is taken, the mistakes from the
# original input will also go into the new file.
#
# Some trouble messages go to stderr.
# If something really bad is encountered an exception is thrown.
#
# This code handles only the Gregorian calendar with epoch setting of BCE
#
# Specs at https://gedcom.io/specs/
#
# This code is released under the MIT License: https://opensource.org/licenses/MIT
# Copyright (c) 2021 John A. Andrea

import sys
import copy
import re
import datetime

# v7.0 requires this character sequence at the start of the file.
# It may also be present in older versions (RootsMagic does include it).
FILE_LEAD_CHAR = '\ufeff'

# The "x" becomes a "startwsith" comparison
SUPPORTED_VERSIONS = [ '5.5', '5.5.1', '7.0.x' ]

# Section types, listed in order or at least header first and trailer last.
# Some are not valid in 5.5.x, but that's ok if they are not found.
# Including a RootsMagic specific: _evdef
SECT_HEAD = 'head'
SECT_INDI = 'indi'
SECT_FAM = 'fam'
SECT_TRLR = 'trlr'
SECTION_NAMES = [SECT_HEAD, 'subm', SECT_INDI, SECT_FAM, 'obje', 'repo', 'snote', 'sour', '_evdef', SECT_TRLR]

# Sections to be created by the parsing
PARSED_INDI = 'individuals'
PARSED_FAM = ' families'

# From 7.0.1 spec pg 40
FAM_EVENT_TAGS = ['anul','cens','div','divf','enga','marb','marc','marl','mars','marr','even']

# From 7.0.1 spec pg 44
INDI_EVENT_TAGS = ['bapm','barm','basm','bles','buri','cens','chra','conf','crem','deat','emig','fcom','grad','immi','natu','ordn','prob','reti','will','adop','birt','chr','even']

# Other individual tags of interest placed into parsed section,
# in addition to the event tags and of course the name(s)
OTHER_INDI_TAGS = ['sex', 'exid', 'fams', 'famc']

# Other family tag of interest placed into parsed section,
# in addition to the event tags
FAM_MEMBER_TAGS = ['husb', 'wife', 'chil']
OTHER_FAM_TAGS = []

# The spec says these items can occur more than once.
# A warning will be output if a second record is detected.

# Individual records which are only allowed to occur once.
# An exception will be thrown if a duplicate is found.
# However they will still be placed into a parsed array to be consistent
# with the other facts/events.
# Use of a validator is recommended.
ONCE_INDI_TAGS = ['sex', 'exid']

# Family items once.
# See the individual for individuals.
ONCE_FAM_TAGS = ['husb','wife']

# There are other important records, such as birth and death which are allowed
# to occur more than once.
# A meta-structure will be added to each individual pointing to the "best" event,
# the first one, or the first proven one, or the first primary one.
BEST_EVENT_KEY = 'best-events'

# Tags for proof and primary in the case of multiple event records.
# These are RootsMagic specific. A future version might try to detect the product
# which produced the export.
EVENT_PRIMARY_TAG = '_prim'
EVENT_PRIMARY_VALUE = 'y'
EVENT_PROOF_TAG = '_proof'
EVENT_PROOF_DEFAULT = 'other'
EVENT_PROOF_VALUES = {'disproven':-1, EVENT_PROOF_DEFAULT:0, 'proven':1 }

# Name sub-parts in order of display appearance
LEVEL2_NAMES = ['npfx', 'givn', 'surn', 'nsfx']

# This code doesn't deal with calendars, but need to know what to look for
CALENDAR_NAMES = [ 'gregorian', 'hebrew', 'julian', 'french_r' ]

# From 7.0.3 spec pg 21
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

# Names, zero included in the zero'th index location for lookup 1 based
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

# dd mmm yyyy
TODAY = datetime.datetime.now().strftime("%d %b %Y")

# Settings for the privatize flag
PRIVATIZE_FLAG = 'privatized'
PRIVATIZE_OFF = 0
PRIVATIZE_MIN = PRIVATIZE_OFF + 1
PRIVATIZE_MAX = PRIVATIZE_MIN + 1

# Some checking to help prevent typos.
# I don't imagine it causes much of a performance hit
SELF_CONSISTENCY_CHECKS = True
SELF_CONSISTENCY_ERR = 'Program code inconsistency:'

# The detected version of the input
version = ''


def string_like_int( s ):
    # If a string contains a non-digit - it doesn't look like an integer
    if re.search( r'\D', s ):
       return False
    return True


def comparable_before_today( years_ago ):
    # Return yyyymmdd for a date years ago.
    # The leap year approximation is ok, this isn't for exact comparisons.
    leap_days = years_ago % 4
    old_date = datetime.datetime.now() - datetime.timedelta( days = (365 * years_ago) + leap_days )
    return '%4d%02d%02d' % ( old_date.year, old_date.month, old_date.day )


def strip_lead_chars( line ):
    return line.replace( FILE_LEAD_CHAR, '' )


def month_name_to_number( month_name ):
	if month_name and month_name.lower() in MONTH_NUMBERS:
		return MONTH_NUMBERS[month_name.lower()]
	return 0


def add_file_back_ref( file_tag, file_index, parsed_section ):
    # Map back from the parsed section to the correcponding record in the
    # data read from directly from the input file.
    parsed_section['file_record'] = { 'key':file_tag, 'index':file_index }


def copy_section( from_sect, to_sect, data ):
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
    # Spec says "@" + xref + "@", so remove the @ and change to lowercase leaving the "i"
    # Ex. from "@i123@" get "i123"
    return tag.replace( '@', '' ).lower().replace( ' ', '' )


def extract_fam_id( tag ):
    # See extract_indi_id
    return tag.replace( '@', '' ).lower().replace( ' ', '' )


def output_sub_section( level, outf ):
    print( level['in'], file=outf )
    for sub_level in level['sub']:
        output_sub_section( sub_level, outf )


def output_section( section, outf ):
    # Output the original un-parsed data
    for level in section:
        output_sub_section( level, outf )


def output_original( version, data, file ):
    # Essentially a file copy operation of what was in the input file.
    # Except that the major sections might be written in a different order.
    with open( file, 'w' ) as outf:
         if not version.startswith( '5' ):
            print( FILE_LEAD_CHAR, end='' )
         for sect in SECTION_NAMES:
             if sect in data:
                output_section( data[sect], outf )


def get_parsed_year( data ):
    # "data" should be the part of the parsed section down to the "date" index

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
    # Get just the year portion of a date from the parsed data
    #
    # It must exist in the parsed data if the event existed in the input file
    # except that it might exist in an empty state with sub-records

    value = ''

    # The back reference should exist
    # from the input data record to the parsed data related to that record.

    k = lookup['key']
    i = lookup['index']

    if 'date' in parsed_data[k][i]:
       value = get_parsed_year( parsed_data[k][i]['date'] )

    return value


def output_section_no_dates( section, outf ):
    for level in section:
        if level['tag'] != 'date':
           print( level['in'], file=outf )
           output_section_no_dates( level['sub'], outf )


def output_privatized_section( level0, priv_setting, event_list, parsed_data, outf ):
    # 'level0' is in the non-parsed section
    # 'parsed_data' is the parsed section for this individual or family

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
    output_privatized_section( level0, priv_setting, INDI_EVENT_TAGS, data_section, outf )


def output_privatized_fam( level0, priv_setting, data_section, outf ):
    output_privatized_section( level0, priv_setting, FAM_EVENT_TAGS, data_section, outf )


def check_section_priv( item, data ):
    return data[item][PRIVATIZE_FLAG]


def check_fam_priv( fam, data ):
    return check_section_priv( extract_fam_id( fam ), data[PARSED_FAM] )


def check_indi_priv( indi, data ):
    return check_section_priv( extract_indi_id( indi ), data[PARSED_INDI] )


def output_privatized( data, file ):
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
    # Return a dict of
    # {
    #  in:exact input line from the file,
    #  tag: the second item on the input line lowercased,
    #  value: input line after tag (or None),
    #  sub: empty array to be used for sub elements
    #  parsed: { key:'string', index:int }
    #         as a map into the parsed section,
    #         not all lines are in parsed section
    # }
    #
    # example:
    # 1 CHAR IBM WINDOWS
    # becomes
    # { n:x, in:'1 CHAR IBM WINDOWS', tag:'char', value:'IBM WINDOWS', sub:[] }
    #
    # example:
    # 0 @I32@ INDI
    # becomes
    # { n:x, in:'0 @I32@ INDI', tag:'@i32@', value:'INDI', sub:[] }
    #
    # example:
    # 2 DATE 14 DEC 1895
    # becomes
    # { n:x, in:'2 DATE 14 DEC 1895', tag:'date', value:'14 DEC 1895', sub:[] }

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


def date_to_comparable( given ):
    # Convert a date to a string of format "yyyymmdd" which is used
    # in comparison with other such dates.
    #
    # The prefix may contain "gregorian"
    # the suffix may contain "bce"
    # otherwise the date should be well formed, i.e. valid digits and valid month name. See the gedcom spec.
    # Given 7 nov 1996 return 19961107 as a string
    # given nov 1996 return 19961101
    # given 1996 return 19960101
    # given "" return ""
    #
    # A malformed portion may be converted to a "1", or might throw an exception
    # if the bad date crash flag is set.

    default_day = 1
    default_month = 1
    default_year = 1

    result = None

    date = given.lower().replace( '  ', ' ' ).replace( '  ', ' ' ).strip()
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
             raise ValueError( DATE_ERR + ':' + str(given) )
          print( DATE_ERR, given, ': setting to', year, month, day, file=sys.stderr )

       if isinstance(day,str):
          #i.e. has been extracted from the given date string
          if string_like_int( day ):
             day = int( day )
             if day < 1 or day > 31:
                day = default_day
                if CRASH_ON_BAD_DATE:
                   raise ValueError( DATE_ERR + ':' + str(given) )
                print( DATE_ERR, given, ': setting day to', day, file=sys.stderr )
          else:
             if CRASH_ON_BAD_DATE:
                raise ValueError( DATE_ERR + ':' + str(given) )
             day = default_day
             print( DATE_ERR, given, ': setting day to', day, file=sys.stderr )

       if isinstance(month,str):
          #i.e. has been extracted from the given date string
          if month in MONTH_NUMBERS:
             month = month_name_to_number( month )
          else:
             print( DATE_ERR, given, ': attempting to correct', file=sys.stderr )
             month = month.replace( '-', '' ).replace( '.', '' )
             if month in MONTH_NUMBERS:
                month = month_name_to_number( month )
             else:
                if CRASH_ON_BAD_DATE:
                   raise ValueError( DATE_ERR + ':' + str(given) )
                month = default_month
                print( DATE_ERR, given, ': setting month to number', month, file=sys.stderr )

       if isinstance(year,str):
          #i.e. has been extracted from the given date string
          if string_like_int( year ):
             year = int( year )
          else:
             print( DATE_ERR, given, ': attempting to correct', file=sys.stderr )
             # Ancestry mistakes
             year = year.replace( '-', '' ).replace( '.', '' )
             if string_like_int( year ):
                year = int( year )
             else:
                if CRASH_ON_BAD_DATE:
                   raise ValueError( DATE_ERR + ':' + str(given) )
                year = default_year
                print( DATE_ERR, given, ': setting year to:', year, file=sys.stderr )

       result = '%4d%02d%02d' % ( year, month, day )

    return result


def date_to_structure( given ):
    # Dates can be saved in a variety of formats: 7.0.1 spec pg 22
    # A year is required or the whole date must be empty
    # return a dict containing a structure with ranges and modifiers
    # containing:
    # - given
    # - is_known - the date contains at least a year, that is: not empty
    #              This is because a date sub-structure can contain date hints
    #              even though its not exactly known.
    # - is_range - spec'ed as datePeriod or between/and dateRange
    # - min { modifier:, value, year }
    # - max { modifier:, value, year }
    #   where modifier is blank, "bef", "aft", "abt", etc.
    #   where value is a string in comparable format yyyymmyy
    #   where year is an int.
    # If date is not given as a range, min and max are set to the same values.

    value = dict()
    value['is_known'] = False

    if given:
       given = given.lower().replace( '  ', ' ' ).replace( '  ', ' ' ).strip()

    if given:
       value['is_known'] = True

       value['is_range'] = False
       value['given'] = given
       value['min'] = dict()
       value['max'] = dict()
       value['min']['modifier'] = ''
       value['max']['modifier'] = ''

       # Ranges cannot contain modifiers such as before, after, etc.,
       # use the "from" / "to", etc. instead

       if 'from ' in given and ' to ' in given:
          value['is_range'] = True
          parts = given.replace( 'from ', '' ).split( ' to ' )
          value['min']['value'] = date_to_comparable( parts[0] )
          value['max']['value'] = date_to_comparable( parts[1] )
          value['min']['modifier'] = 'from'
          value['max']['modifier'] = 'to'

       elif 'bet ' in given and ' and ' in given:
          value['is_range'] = True
          parts = given.replace( 'bet ', '' ).split( ' and ' )
          value['min']['value'] = date_to_comparable( parts[0] )
          value['max']['value'] = date_to_comparable( parts[1] )
          value['min']['modifier'] = 'bet'
          value['max']['modifier'] = 'and'

       elif given.startswith( 'to ' ):
          # Seems like this specifies everything up to the date
          # why use this instead of 'before'
          value['min']['value'] = date_to_comparable( given.replace( 'to ', '' ) )
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

          value['min']['value'] = date_to_comparable( given )

          for item in ['value','modifier']:
              value['max'][item] = value['min'][item]

       for item in ['min','max']:
           if value[item]['value']:
              value[item]['year'] = int( value[item]['value'][0:4] )
           else:
              value[item]['year'] = None

    return value


def convert_to_unicode( text ):
    # The file was opened with utf-8 encoding, so these alt characters come in as high bit values.
    # These are the characters in my family, more could be added.
    text = text.replace( '\xe7', '\\u00e7' ) #c cedilia
    text = text.replace( '\xe9', '\\u00e9' ) #e acute
    text = text.replace( '\xc9', '\\u00c9' ) #E acute
    text = text.replace( '\xe8', '\\u00e8' ) #e agrave
    text = text.replace( '\xe1', '\\u00e1' ) #a acute
    text = text.replace( '\xc1', '\\u00c1' ) #A acute
    text = text.replace( '\xe0', '\\u00e0' ) #a agrave
    return text


def convert_to_html( text ):
    # The file was opened with utf-8 encoding, so these alt characters come in as high bit values.
    # These are the characters in my family, more could be added.
    text = text.replace( '<', '&lt;' )
    text = text.replace( '>', '&gt;' )
    text = text.replace( '\xe7', '&#231;' ) #c cedilia
    text = text.replace( '\xe9', '&#233;' ) #e acute
    text = text.replace( '\xc9', '&#201;' ) #E acute
    text = text.replace( '\xe8', '&#232;' ) #e agrave
    text = text.replace( '\xe1', '&#225;' ) #a acute
    text = text.replace( '\xc1', '&#193;' ) #A acute
    text = text.replace( '\xe0', '&#224;' ) #a agrave
    return text


def get_note( level2 ):
    # Pre version 7.0 the note lines were short; requiring continuation lines.
    #
    # There are rules about adding spaces and not stripping spaces from continuation lines. I'm not sure I'm handling that correctly.
    #
    # v7.0.1 introduces the "cont" tag which might require newlines between records

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
    # Note that custom event records with the tag "even" are not included
    # because of the the associated even.type

    out_data[BEST_EVENT_KEY] = dict()

    # find the smallest of the options
    smallest = min( EVENT_PROOF_VALUES.values() ) - 1

    # No further tests for the "best" of these ones
    # Strictly here for consistency
    for tag in always_first_list:
        if tag in out_data:
           out_data[BEST_EVENT_KEY][tag] = 0

    for tag in event_list:
        if tag != 'even':
           if tag in out_data:
              found_best = 0
              if len( out_data[tag] ) > 1:
                 # what if there is a disproven marked as primary - choose any other

                 # find the best: disproven having lowest value, proven is highest
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
    if value:
       if value.lower() == 'unknown':
          # This is an Ancestry mistake, not sure of the symantics
          value = "bef " + TODAY
    return date_to_structure( value )


def handle_event_tag( tag, level1, out_data ):
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
       if value.lower() == 'y':
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
    # A custom event might look like this
    #
    #1 EVEN 118 cM 2%
    #2 TYPE dna
    #2 DATE 1 aug 2021

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
    # If may be more appropriate to use the name translation in the
    # gedcom data, but only of the records for text/plain and text/html
    # parts exist.

    out_data['display'] = name

    # there may be unicode/non-utf-8 chars
    out_data['html'] = convert_to_html( name )
    out_data['unicode'] = convert_to_unicode( name )


def handle_name_tag( tag, level1, out_data ):
    # Second occurance of the name tag is for the alternate name.

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
    for tag in tag_list:
        if tag in data:
           if len(data[tag]) > 1:
              raise ValueError( DATA_ERR + sect_type + ' ' + ref_id + ' tag occured more than once:' + str(tag) )


def parse_family( level0, out_data ):
    # From the input file date, build up the parsed structure.

    # Use this flag on output of modified data
    out_data[PRIVATIZE_FLAG] = PRIVATIZE_OFF

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
           # broken out specially because its custom style
           # must be handled before the test for general event list
           handle_custom_event( tag, level1, out_data )

        elif tag in FAM_EVENT_TAGS:
           handle_event_tag( tag, level1, out_data )

        if parsed:
           # Map this file record back to the parsed section just created
           level1['parsed'] = { 'key':tag, 'index': len(out_data[tag])-1 }

    ensure_not_twice( ONCE_FAM_TAGS, 'Family', level0['tag'], out_data )
    set_best_events( FAM_EVENT_TAGS, ONCE_FAM_TAGS, out_data )


def setup_parsed_families( sect, psect, data ):
    for i, level0 in enumerate( data[sect] ):
        fam = extract_fam_id( level0['tag'] )
        data[psect][fam] = dict()
        add_file_back_ref( sect, i, data[psect][fam] )

        parse_family( level0, data[psect][fam] )


def parse_individual( level0, out_data ):
    # From the input data, build up the parsed structure.

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
           # these two broken out specially because they use the id extraction
           # must be handled before the test for other-indi-tags
           out_data[tag].append( extract_fam_id( value ) )

        elif tag in OTHER_INDI_TAGS:
           out_data[tag].append( value )

        elif tag == 'even':
           # this one broken out specially because its a custom event
           # must be handled before the test for regular events
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
    for i, level0 in enumerate( data[sect] ):
        indi = extract_indi_id( level0['tag'] )
        data[psect][indi] = dict()
        add_file_back_ref( sect, i, data[psect][indi] )

        parse_individual( level0, data[psect][indi] )


def setup_parsed_sections( data ):
    setup_parsed_families( SECT_FAM, PARSED_FAM, data )
    setup_parsed_individuals( SECT_INDI, PARSED_INDI, data )


def check_parsed_sections( data ):
    # Check xrefs from individuals to families, vise versa, etc.

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
    # Part of the self consistency checks.
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
    # Part of the self consistency checks.
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
    # Part of the self consistency checks.
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
    # Part of the self consistency checks.
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


def set_privatize_flag( data, years_since_death=20, max_lifetime=104 ):
    # Used to output the original data, but skipping some records based on
    # the years since the person has died.
    #
    # Parameters are:
    #
    # years_since_death -> 20 is a reasonable value.
    #                   If the person died before this many years: -> OFF
    #                      no hiding events
    #                   If the person died since this many years: -> MIM
    #                      show only years rather than exact dates
    #
    # max_lifetime -> the longest that any person is expected to live.
    #                 105 is a resonable value. It a person was born that many years
    #                 ago, assume they are now deceased. The years_since_death
    #                 test is then applied.
    #
    # If a person has no death record and was born less than max_lifetime (or no
    # birth record) assume they are still living: -> MAX
    #     hide event dates and related sub-structures
    #     and show events occured with a flagged event such as "1 BIRT Y".
    #
    # The setting is OFF for everyone unless this routine is called.
    #
    # It is possible to guess that ancestors might be deceased based on births of
    # descendants - those calculations are not made, only the known event facts
    # are considered.

    if SELF_CONSISTENCY_CHECKS:
       if not isinstance(years_since_death,int):
          raise ValueError( SELF_CONSISTENCY_ERR + 'years_since_death is not an int' )
       if not isinstance(max_lifetime,int):
          raise ValueError( SELF_CONSISTENCY_ERR + 'max_lifetime is not an int' )

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

        # pre 7.0, line leading spaces were allowed

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

              elif lc_line.startswith( '0 _evdef' ):
                 sect = '_evdef'

              else:
                 sect = '?'

              if sect != SECT_HEAD:
                 # Test for version as soon as header is finished
                 if not version:
                    version = confirm_gedcom_version( data )

              if sect not in SECTION_NAMES:
                 raise ValueError( 'Unknown section:' + str(line) )

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
    # From "datafile" name into returned dict.
    # See the related document for the format of the dict.

    if SELF_CONSISTENCY_CHECKS:
       # Ensure no conflict between the section names.
       for sect in SECTION_NAMES:
           for parsed_sect in [PARSED_INDI, PARSED_FAM]:
               if sect.lower().strip() == parsed_sect.lower().strip():
                  raise ValueError( SELF_CONSISTENCY_ERR + 'section name duplication:' + str(sect) )
       ensure_lowercase_constants()


    # The file read into a data structure.
    data = dict()

    # These are the zero level tags expected in the file.
    # Some may not occur.
    for sect in SECTION_NAMES:
        data[sect] = []

    # Sections to be created.
    for sect in [PARSED_INDI, PARSED_FAM]:
        data[sect] = dict()

    with open( datafile, encoding='utf-8' ) as inf:
         read_in_data( inf, data )

    if len( data[SECT_HEAD] ) != 1:
       raise ValueError( DATA_ERR + 'Header must occur once and only once.' )
    if len( data[SECT_TRLR] ) != 1:
       raise ValueError( DATA_ERR + 'Trailer must occur once and only once.' )

    if len( data[SECT_INDI] ) < 1:
       raise ValueError( DATA_ERR + 'No individuals' )
    if len( data[SECT_FAM] ) < 1:
       # This is not a fatal problem, only a warning
       print( DATA_WARN, 'No families', file=sys.stderr )

    # Since the data passed are serios tests; form the other portion of the data
    setup_parsed_sections( data )

    # and do some checking
    check_parsed_sections( data )

    return data
