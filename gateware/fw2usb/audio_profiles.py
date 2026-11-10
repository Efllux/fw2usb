"""Conservative stereo48k subsets of PR17 identity candidates.
No model-name channel-count inference: runtime-discovered AM824 positions and
firmware identity are mandatory. This does not implement vendor mixer controls.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class AudioProfile:
    name: str
    family: str
    vendor: int
    model: int
    rate: int=48000
    channels: int=2

    def bind(self, *, vendor, model, firmware, rate, capture_pcm_positions, playback_pcm_positions):
        if (vendor,model,rate)!=(self.vendor,self.model,self.rate) or not firmware:
            raise ValueError('identity/rate/firmware mismatch')
        maps=[]
        for positions in (capture_pcm_positions,playback_pcm_positions):
            if len(positions)<2 or len(set(positions))!=len(positions) or any(p<0 or p>254 for p in positions):
                raise ValueError('discovered PCM layout does not support stereo subset')
            maps.append(tuple(positions[:2]))
        return dict(profile=self.name,firmware=firmware,rate=rate,capture=maps[0],playback=maps[1])

FIREBOX=AudioProfile('presonus-firebox-stereo48','bebob',0x000a92,0x00010000)
KONNEKT6=AudioProfile('desktop-konnekt6-stereo48','dice',0x000166,0x00000024)
PROFILES=(FIREBOX,KONNEKT6)
