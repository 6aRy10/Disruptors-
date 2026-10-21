from dataclasses import dataclass

@dataclass
class DemoState:
    version:int=1
    hwa_capacity:int=9500
    hwa_committed:int=2000
    supplier_confirmed:bool=False
    def confirm_capacity(self,new_capacity:int)->int:
        if new_capacity<0: raise ValueError('capacity must be >=0')
        if new_capacity!=self.hwa_capacity or not self.supplier_confirmed:
            self.hwa_capacity=new_capacity; self.supplier_confirmed=True; self.version+=1
        return self.version
    @property
    def hwa_available(self): return max(0,self.hwa_capacity-self.hwa_committed)
