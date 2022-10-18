@echo off

if exist r.out del r.out
if exist r.err del r.err

read.py family.ged >r.out 2>r.err