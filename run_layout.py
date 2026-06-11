from piply_opdf.phases.phase1_assess import Phase1Assessor
from piply_opdf.phases.phase2_enhance import Phase2Enhancer
from piply_opdf.phases.phase3_layout import Phase3Layout

print("Processing 134242485947340351.pdf...")
assessor1 = Phase1Assessor()
assessor1.assess('134242485947340351.pdf', '134242485947340351_piply')
enhancer1 = Phase2Enhancer()
enhancer1.enhance('134242485947340351_piply')
layout1 = Phase3Layout()
layout1.detect_layout('134242485947340351_piply')

print("Processing sample.pdf...")
assessor2 = Phase1Assessor()
assessor2.assess('sample.pdf', 'sample_piply')
enhancer2 = Phase2Enhancer()
enhancer2.enhance('sample_piply')
layout2 = Phase3Layout()
layout2.detect_layout('sample_piply')
print("Done!")
