@echo off

if exist 1.out del 1.out
if exist 1.err del 1.err
if exist 2.out del 2.out
if exist 2.err del 2.err
if exist 3.out del 3.out
if exist 3.err del 3.err

test-custom-event-value.py >1.out 2>1.err

test-exist-custom-event.py >2.out 2>2.err

test-exist-date-and-place.py >3.out 2>3.err