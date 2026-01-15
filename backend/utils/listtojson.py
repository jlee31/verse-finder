import json

input_str = "AdmirationAdorationAestheticAppreciationAmusementAngerAwewkwardnesBoredomCalmnessConfusionCravingDisgustEmpathicPainEntrancementExcitementFearHorrorInterestJoyNostalgiaReliefRomanceSadnessSatisfactionSexualDesireSurprise"

output = []
start = 0

for i in range(1, len(input_str)):
    if input_str[i].isupper():
        output.append(input_str[start:i])
        start = i

output.append(input_str[start:])

with open('../../data/emotions.json', 'w') as f:
    json.dump(output, f, indent=2)
