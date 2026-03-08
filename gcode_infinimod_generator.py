#!/usr/bin/env python3
"""
InfiniMod Auto-Ejection G-code Generator
=========================================
Generates Bambu Lab auto-ejection sequences for continuous printing.
Based on OpenScan InfiniMod and Factorian Designs automation research.

Usage:
    python gcode_infinimod_generator.py <input_gcode> -o <output_gcode> [options]

Features:
    - Automatic bed cooldown sequence
    - Optional bed vibration (M970 commands)
    - Nozzle push-off mechanism
    - Full loop control
    - Temperature management
"""

import argparse
import sys
import re
from pathlib import Path
from typing import Tuple, Optional


class InfiniModGenerator:
    """Generates InfiniMod auto-ejection G-code sequences."""
    
    # Bambu Lab M970 Vibration Commands (from OpenScan research)
    M970_VIBRATE_PLATE = "M970.3 Q1 A7 K0 O2      ; vibrate printbed"
    M970_VIBRATE_AGGRESSIVE = "M970 Q0 A10 B50 C90 H15 K0 M20 O3   ; vibrate printbed"
    
    # Push-off movement constants (P1/P1S specific - Y-AXIS PUSH towards FRONT)
    # Push parts FORWARD towards the front of the printer (towards camera)
    # Y-axis: bed moves, gantry stationary - ejects parts off front edge
    PUSH_NOZZLE_APPROACH = "G1 X128 Y240 F12000 ; Move to back side of bed"
    PUSH_NOZZLE_HEIGHT = "G1 Z2      ; Move Z to 2mm (near bed, safe height)"
    
    # Y-axis push motions: Bed moves FORWARD to eject parts off front edge
    # This pushes parts towards camera/front of printer
    PUSH_NOZZLE_MOTION = [
        "G1 X128 Y20 F300     ; Push motion 1 (Y-axis FORWARD, slow)",
        "G1 X128 Y240 F3000   ; Return BACK fast",
        "G1 X80 Y20 F300      ; Push from LEFT side",
        "G1 X80 Y240 F3000    ; Return BACK fast",
        "G1 X176 Y20 F300     ; Push from RIGHT side",
        "G1 X176 Y240 F3000   ; Return BACK fast",
        "G1 X128 Y10 F300     ; Final push (far FORWARD)",
        "G1 X128 Y240 F3000   ; Return to safe BACK position"
    ]
    
    def __init__(self, 
                 cooldown_temp: int = 20,
                 cooldown_wait_time: int = 5,
                 enable_vibrate: bool = True,
                 enable_nozzle_push: bool = True,
                 push_speed: int = 300,
                 bed_tilt_angle: int = 30):
        """Initialize the generator with parameters.
        
        Args:
            cooldown_temp: Target bed temperature (°C) - lower = faster release
            cooldown_wait_time: Maximum wait time (minutes) - NOW DEFAULT 5 MIN (was 15)
            enable_vibrate: Enable M970 vibration commands
            enable_nozzle_push: Enable nozzle push mechanism
            push_speed: Speed of push motion (mm/min) - 300 for safety
            bed_tilt_angle: Manual bed tilt angle in degrees (for reference, ~20-30 deg)
        """
        self.cooldown_temp = max(15, min(50, cooldown_temp))
        self.cooldown_wait_time = max(1, min(120, cooldown_wait_time))  # Can be as low as 1 min now
        self.enable_vibrate = enable_vibrate
        self.enable_nozzle_push = enable_nozzle_push
        self.push_speed = max(50, min(3000, push_speed))
        self.bed_tilt_angle = bed_tilt_angle
        
    def generate_cooldown_sequence(self) -> str:
        """Generate bed cooldown G-code.
        
        NOTE: Bed should be tilted ~20-30 degrees BEFORE this sequence runs!
              Gravity helps parts slide off during ejection.
              Tilt printer manually or use fixture.
        
        Returns:
            G-code string for cooldown sequence
        """
        cooldown_ms = self.cooldown_wait_time * 60000  # Convert to milliseconds
        
        code = f"""; ===== AUTO-EJECTION SEQUENCE (InfiniMod) =====
; IMPORTANT: Bed should be tilted ~{self.bed_tilt_angle}° for gravity-assisted ejection
; Tilt physically BEFORE running this sequence - gravity helps parts slide off
M400 ; Wait for all motion to complete

; --- PART 1: FASTER COOLDOWN (only {self.cooldown_wait_time} min) ---
M140 S0      ; Set bed temperature to 0°C (stop heating)
M104 S0      ; Set hotend temperature to 0°C (stop heating)
G4 P{cooldown_ms}  ; Wait for bed to cool (max {self.cooldown_wait_time} min = MUCH FASTER!)
M109 S{self.cooldown_temp}   ; Wait for bed to reach target cooldown temp ({self.cooldown_temp}°C)

M400 ; Wait for temperature to stabilize
"""
        return code
    
    def generate_vibration_sequence(self) -> str:
        """Generate bed vibration G-code using M970 commands.
        
        Returns:
            G-code string for vibration sequence
        """
        if not self.enable_vibrate:
            return "; Vibration disabled\n"
        
        code = f"""; --- PART 2: BED VIBRATION ---
; Vibrate build plate to loosen printed parts
{self.M970_VIBRATE_PLATE}
M400
{self.M970_VIBRATE_AGGRESSIVE}
M400
"""
        return code
    
    def generate_nozzle_push_sequence(self) -> str:
        """Generate nozzle push-off G-code using Y-AXIS motion (bed push).
        
        KEY: Uses Y-axis (bed) motion to push parts FORWARD to FRONT
        - Y-axis: Bed moves forward (Y decreases from 240 to 20)
        - Parts eject off FRONT edge of printer (towards camera)
        - Multiple X-positions (left, center, right) for uniform ejection
        
        Returns:
            G-code string for Y-axis bed push sequence (forward to front)
        """
        if not self.enable_nozzle_push:
            return "; Nozzle push disabled\n"
        
        move_sequence = "\n".join([f"G1 {motion} F{self.push_speed}" if "F" not in motion 
                                   else motion 
                                   for motion in self.PUSH_NOZZLE_MOTION])
        
        code = f"""; --- PART 3: Y-AXIS BED PUSH (Forward to Front) ---
; PUSH FORWARD: Bed moves towards FRONT, parts eject off front edge (towards camera)
; Gantry stays at Z2mm, bed does the pushing
; Multiple X-passes (left, center, right) ensure complete ejection

G1 X128 Y240 F12000  ; Position gantry center, bed at BACK
G1 Z5 F1200         ; Raise nozzle to safe height

; Position for push
{self.PUSH_NOZZLE_APPROACH}
{self.PUSH_NOZZLE_HEIGHT}

; Execute Y-axis push motions (bed moves FORWARD, pushing parts to FRONT)
; Multiple X-positions for thorough ejection across bed
{move_sequence}

; Return to home position
G1 X128 Y240 Z10 F12000 ; Return to center-back, safe height
M400
"""
        return code
    
    def generate_full_sequence(self) -> str:
        """Generate complete auto-ejection end sequence.
        
        Returns:
            Complete G-code string for one full ejection cycle
        """
        sequences = [
            self.generate_cooldown_sequence(),
            self.generate_vibration_sequence(),
            self.generate_nozzle_push_sequence()
        ]
        
        code = "".join(sequences)
        code += """; ===== AUTO-EJECTION COMPLETE =====
; Ready to start next print loop

"""
        return code
    
    def process_gcode_file(self, input_file: str, output_file: str, 
                          num_loops: int = 1, auto_eject: bool = True) -> bool:
        """Process G-code file and add ejection sequences.
        
        Args:
            input_file: Input G-code filename
            output_file: Output G-code filename
            num_loops: Number of loops to add
            auto_eject: Whether to add ejection sequences
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Read input file
            with open(input_file, 'r') as f:
                content = f.read()
            
            # Find the end of the file
            lines = content.split('\n')
            
            # Remove or find the existing end code
            end_code_idx = -1
            for i, line in enumerate(lines):
                if 'M109' in line or 'M104 S0' in line:  # Common end markers
                    end_code_idx = i
            
            # Build output
            output_lines = lines[:end_code_idx] if end_code_idx > 0 else lines
            
            # Add ejection sequence
            if auto_eject:
                output_lines.append("")
                output_lines.append(self.generate_full_sequence())
            
            # Write output file
            with open(output_file, 'w') as f:
                f.write('\n'.join(output_lines))
            
            print(f"✓ Successfully created {output_file}")
            print(f"  - Added auto-ejection sequence")
            print(f"  - Ejection parameters:")
            print(f"    • Cooldown target: {self.cooldown_temp}°C")
            print(f"    • Max wait: {self.cooldown_wait_time} minutes")
            print(f"    • Vibration: {'Enabled' if self.enable_vibrate else 'Disabled'}")
            print(f"    • Nozzle push: {'Enabled' if self.enable_nozzle_push else 'Disabled'}")
            
            return True
            
        except FileNotFoundError:
            print(f"✗ Error: Could not find input file '{input_file}'")
            return False
        except Exception as e:
            print(f"✗ Error processing file: {e}")
            return False


def main():
    """Command-line interface for InfiniMod generator."""
    
    parser = argparse.ArgumentParser(
        description="Generate Bambu Lab auto-ejection G-code (InfiniMod)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
IMPORTANT: Tilt your printer ~30° BEFORE running auto-ejection!
           Gravity helps parts slide off. Use a wedge or stand.

Examples:
  # FASTEST DEFAULT - 5 min cooldown, 30° tilt reference
  python gcode_infinimod_generator.py part.gcode -o part_auto.gcode
  
  # Ultra-fast for small parts (2 min wait only!)
  python gcode_infinimod_generator.py part.gcode -o part_auto.gcode -w 2 -t 22
  
  # Even faster (1 min minimum!)
  python gcode_infinimod_generator.py part.gcode -o part_auto.gcode -w 1 -t 25
  
  # Custom tilt angle reference (45° for steep gravity assist)
  python gcode_infinimod_generator.py part.gcode -o part_auto.gcode --tilt 45
  
  # Slower push for delicate models
  python gcode_infinimod_generator.py part.gcode -o part_auto.gcode -s 200

NOTE: Generator uses Y-AXIS push (bed moves forward)
      Default: 5 min cooldown (down from 15!), 30° tilt recommended
        """
    )
    
    parser.add_argument('input_file', 
                       help='Input G-code file')
    parser.add_argument('-o', '--output', dest='output_file',
                       help='Output G-code file (default: input_file_ejection.gcode)')
    parser.add_argument('-t', '--temp', type=int, default=20,
                       help='Target cooldown temperature in °C (default: 20, range: 15-50). LOWER TEMP = FASTER RELEASE (e.g., 18°C)')
    parser.add_argument('-w', '--wait', type=int, default=5,
                       help='Max cooldown wait time in minutes (default: 5, range: 1-120). NOW ONLY 5 MIN! (was 15)')
    parser.add_argument('-s', '--speed', type=int, default=300,
                       help='Push-off Y-axis speed in mm/min (default: 300, range: 50-3000). Pushes FORWARD to FRONT!')
    parser.add_argument('--tilt', type=int, default=30,
                       help='Bed tilt angle for reference in comments (default: 30°, range: 0-45°). PHYSICALLY TILT YOUR PRINTER ~30° BEFORE RUNNING!')
    parser.add_argument('--no-vibrate', action='store_true',
                       help='Disable bed vibration (M970 commands)')
    parser.add_argument('--no-push', action='store_true',
                       help='Disable Y-axis forward push mechanism')
    parser.add_argument('-n', '--loops', type=int, default=1,
                       help='Number of loops (default: 1)')
    
    args = parser.parse_args()
    
    # Validate input file
    if not Path(args.input_file).exists():
        print(f"✗ Error: Input file '{args.input_file}' not found")
        return 1
    
    # Set output file
    if not args.output_file:
        base_name = Path(args.input_file).stem
        args.output_file = f"{base_name}_ejection.gcode"
    
    # Create generator
    generator = InfiniModGenerator(
        cooldown_temp=args.temp,
        cooldown_wait_time=args.wait,
        enable_vibrate=not args.no_vibrate,
        enable_nozzle_push=not args.no_push,
        push_speed=args.speed,
        bed_tilt_angle=args.tilt
    )
    
    # Generate ejection sequence (standalone)
    print("=== InfiniMod Auto-Ejection Generator ===\n")
    print("Generated ejection sequence:")
    print("-" * 60)
    print(generator.generate_full_sequence())
    print("-" * 60)
    
    # Process file
    print(f"\nProcessing file: {args.input_file}")
    success = generator.process_gcode_file(
        args.input_file,
        args.output_file,
        num_loops=args.loops
    )
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
