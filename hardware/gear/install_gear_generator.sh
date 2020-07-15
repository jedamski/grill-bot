# First, download the tool we're going to use to generate the gear dxf
if [ ! -d "gear-profile-generator" ]; then
  git clone --branch python3_support https://github.com/leventelist/gear-profile-generator.git
fi

# Now call the script twice to generate the dxf files
mkdir geometry
cd gear-profile-generator
python3 gear.py --teeth-count=9  --tooth-width=0.2715233655 --pressure-angle=15 --backlash=0.0 -t=dxf -o=../geometry/gear_small.dxf
python3 gear.py --teeth-count=16 --tooth-width=0.2715233655 --pressure-angle=15 --backlash=0.0 -t=dxf -o=../geometry/gear_large.dxf
