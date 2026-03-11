import numpy as np


class GetData:
    def __init__(self, n_instance: int, n_items: int, bin_capacity: int):
        """
                                                                    

             
                                                        
                                     
                                               
        """
        self.n_instance = n_instance
        self.n_items = n_items
        self.bin_capacity = bin_capacity

    def generate_instances(self):
        """
                                                          

                
                                                        
                                                   
                                                     
        """
        np.random.seed(2024)                                
        instance_data = []

        for _ in range(self.n_instance):
                                                  
            alpha = 2                                      
            beta = 5                                      

                                                                    
                                                             
            item_weights = (50 - np.random.beta(alpha, beta, size=self.n_items) * 40).astype(int).tolist()
                                                                                       
                                                                                

                                                                           
                                                                        

                                                         
                                                                                                               

            instance_data.append((item_weights, self.bin_capacity))

        return instance_data

                  
                                                                      
                                                 
                            
                     
