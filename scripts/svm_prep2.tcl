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

proc analyzeEnergy {f a b} {
  snack::sound s
  s read $f
  s crop [expr int($a*[s cget -rate])] [expr int($b*[s cget -rate])]
  set samplePos 0
  set length [s length]

  set avg 0.0
  set min 0
  set max 0
  set var 0
  set len 0
  set energies { }

  while {$samplePos < $length-160} {
    set energy 0
    set i 0
    while {$i < 160} {
      set energy [expr {$energy+pow([s sample [expr {$samplePos+$i}]],2)}]
      incr i 1
    }
    set energy [expr {double($energy)/160}]
    
    if { $energy > 0 } {
      set avg [expr {$avg + $energy}]
      incr len 1
      lvarpush energies $energy
    }

    if { $samplePos == 160 } {
      set min $energy
      set max $energy
    } else {
      if { $energy > $max } {
        set max $energy
      } elseif { $energy < $min && $energy > 0 } {
        set min $energy
      }
    }

    incr samplePos 160
  }

  if {$len <= 1} {
    set avg 0
    set var 0
  } else {
    set avg [expr {double($avg)/$len}]

    for {set j 0} {$j < $len} {incr j} {
      set var [expr {$var + pow(([lvarpop energies] - $avg),2)}]
    }

    set var [expr {sqrt($var/($len-1))}]
  }

  return [concat $avg $min $max $var]
}

proc analyzePitch {f a b} {
  snack::sound s
  s read $f
#  puts "rate: [s cget -rate], samples: [s length -unit SAMPLES], seconds: [s length -unit SECONDS]"
  s crop [expr int($a*[s cget -rate])] [expr int($b*[s cget -rate])]
  set samplePos 0
  set length [s length]

  set avg 0.0
  set min 0
  set max 0
  set var 0
  set len 0
  set prevpitch 0
  set pitches { }
  set data [s pitch -method esps]

#  while {$samplePos < $length - (666-1*320)} 
#    t copy s -start $samplePos -end [expr {$samplePos+665+1*320}]
#    set pitch [lindex [lindex [t pitch -method esps] 2] 0]
  while {$samplePos < [llength $data]} {
    set pitch [lindex [lindex $data $samplePos] 0]
    if [ and [string is double -strict $pitch] [expr {$pitch>0}] ] {
      if { $len == 0 } {
        set min $pitch
        set max $pitch
      } else {
        if { $pitch > $max } {
          set max $pitch
        } elseif { $pitch < $min && $pitch > 0 } {
          set min $pitch
        }
      }
      set prevpitch $pitch

      incr len 1
      lvarpush pitches $pitch
      set avg [expr {$avg + $pitch}]
    }

#    incr samplePos 160
    incr samplePos 1
  }

  if {$len <= 1} {
    set avg 0
    set var 0
  } else {
    set avg [expr {double($avg)/$len}]

    for {set i 0} {$i < $len} {incr i} {
      set var [expr {$var + pow(([lvarpop pitches] - $avg),2)}]
    }

    set var [expr {sqrt($var/($len-1))}]
  }

  return [concat $avg $min $max $var]
}

proc analyzeFormant { f n a b } {
  snack::sound s
  s read $f
  s crop [expr int($a*[s cget -rate])] [expr int($b*[s cget -rate])]
  set samplePos 0
  set length [s length]
  set n [expr {$n-1}]

  set avg 0.0
  set min 0
  set max 0
  set var 0
  set len 0
  set frmnts { }
  set data [s formant]

#  while {$samplePos < $length - 700} 
#    t copy s -start $samplePos -end [expr {$samplePos+700}]
#    set formant [lindex [lindex [t formant] end] $n]
  while {$samplePos < [llength $data]} {
    set formant [lindex [lindex $data $samplePos] $n]  
    if [ and [string is double -strict $formant] [expr {$formant>0}] ] {
      if { $len == 0 } {
        set min $formant
        set max $formant
      } else {
        if { $formant > $max } {
          set max $formant
        } elseif { $formant < $min } {
          set min $formant
        }
      }

      set avg [expr {$avg+$formant}]
      incr len 1

      lvarpush frmnts $formant
    }

    incr samplePos 1
  }

  if {$len <= 1} {
    set avg 0
    set var 0
  } else {
    set avg [expr {double($avg)/$len}]

    for {set i 0} {$i < $len} {incr i} {
      set var [expr {$var + pow(([lvarpop frmnts] - $avg),2)}]
    }

    set var [expr {sqrt($var/($len-1))}]
  }

  return [concat $avg $min $max $var]
}
  
# 20 features
# * F0-F3 + Energy: Avg, Min, Max, Variance

proc analyzeAll { f a b } {
   return [concat [analyzePitch $f $a $b] [analyzeFormant $f 1 $a $b] [analyzeFormant $f 2 $a $b] [analyzeFormant $f 3 $a $b] [analyzeEnergy $f $a $b]]
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
  set rawdata [analyzeAll [lindex $tmp 0] [lindex $tmp 2] [lindex $tmp 3]]
  if { [lindex $tmp 1] == 0 } {
    set output "$output+1"
  } else {
    set output "$output-1"
  }
  for { set j 0 } { $j < [llength $rawdata] } {incr j} {
    set output "$output [expr {$j+1}]:[lindex $rawdata $j]"
  }
  set output "$output\n"
}

set fp [open [lindex $argv 1] w]
puts $fp $output
close $fp

exit
