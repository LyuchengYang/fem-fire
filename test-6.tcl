# set T_end 600;
# set force 100;

model BasicBuilder -ndm 3 -ndf 6;

# NODAL DEFINITIONS
node 1    0 0 0;
node 2 1000 0 0;

# BOUNDRY CONDITIONS
fix 1  1 1 1  1 1 1;

# Steel material properties
set Es 210000;     # MPa     , steel initial Young's modulus;
set Fy 250;        # MPa     , steel initial yield strength;
set b 0.001;       # %       , strain-hardening  ratio;
set Hiso [expr $b*$Es]; # MPa     , isotropic hardening modulus;
set Hkin 0.0;     # MPa     , kinematic hardening modulus;



set matTag 1;
nDMaterial J2 2 -Fy $Fy -E $Es -nu 0.29 -Hiso [expr $b*$Es] -Fs $Fy -Hsat 0;
# nDMaterial J2BeamFiber 2 $Es 0.27 $Fy $Hiso $Hkin

nDMaterial InitialStrain $matTag 2 0.0

set secTag 1;
set area [expr 100*100/15]
section ShearFiber $secTag {
  foreach y [linspace -50 50 15] {
    fiber $y 0 -area $area -material 1;
  }
}

set beamTransfTag 1;
geomTransf Linear $beamTransfTag 0 0 1;

element ExactFrame 1 {1 2} -section $secTag -transform $beamTransfTag;


pattern Plain 2 Linear {
    load 2   $force 0 0   0 0 0   0;
}

set NstepGravity 10;

constraints Transformation;
numberer RCM;
system UmfPack;
test NormDispIncr 1e-8 10;
algorithm Newton;
integrator LoadControl [expr 1.0/$NstepGravity];
analysis Static;
analyze $NstepGravity;


loadConst -time 0.0

#
# fire analysis
#

set Nstep 1;
set Factor [expr 1.0/$Nstep]; 	# first load increment;


constraints Transformation;
numberer RCM;						# renumber dof's to minimize band-width (optimization)
system UmfPack;

test NormDispIncr 1e-8 1000;

algorithm Newton;					
# algorithm NewtonLineSearch;
# algorithm BFGS;
# algorithm Broyden;
# algorithm KrylovNewton; 
# algorithm Linear;
# algorithm ModifiedNewton;
# algorithm ExpressNewton 20;

integrator LoadControl $Factor;	# determine the next time step for an analysis
analysis Static;			# define type of analysis static or transient
# analyze $Nstep;		# apply fire load


# puts "Fire done"
