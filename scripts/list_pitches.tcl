#!/bin/sh
# the next line restarts using wish \
exec wish8.4 "$0" "$@"

package require snack

proc and {a b} {
  return [expr $a && $b]
}

proc lvarpop {var {ndx 0}} {
  upvar $var args
  set r [lindex $args $ndx]
  set args [lreplace $args $ndx $ndx]
  return $r
}

proc lvarpush {var val {ndx end}} {
  upvar $var args
  set args [linsert $args $ndx $val]
}

proc getPitchesList {f a b} {
  snack::sound s
  s read $f
  s crop [expr int($a*[s cget -rate])] [expr int($b*[s cget -rate])]
  set samplePos 0
  set length [s length]

  set data [s pitch -method esps]
  set pitches { }
  while {$samplePos < [llength $data]} {
    set pitch [lindex [lindex $data $samplePos] 0]
    if [ and [string is double -strict $pitch] [expr {$pitch>0}] ] {
      lvarpush pitches $pitch
    }
    incr samplePos 1
  }

  return $pitches
}

if { $argc < 2 } {
  puts "Usage: $argv0 input.txt output.txt"
  exit 1
}

set data1f [lindex $argv 0]

set fp [open $data1f r]
set data1 [split [read $fp] "\n"]
close $fp

set output ""
for { set i 0 } { $i < [expr {[llength $data1]-1}] } {incr i} {
  set tmp [lindex $data1 $i]
  puts "Analyzing ([lindex $tmp 1]) [expr {$i+1}] / [expr {[llength $data1]-1}]" 
  set rawdata [getPitchesList [lindex $tmp 0] [lindex $tmp 2] [lindex $tmp 3]]
  for { set j 0 } { $j < [llength $rawdata] } {incr j} {
    set output "$output[lindex $rawdata $j] "
  }
  set output "$output\n"
}

set fp [open [lindex $argv 1] w]
puts $fp $output
close $fp

exit
