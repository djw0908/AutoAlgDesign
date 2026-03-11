import numpy as np


class GetData:
    def __init__(self, n_instance: int, n_items: int, knapsack_capacity: int):
        """
                                                              

             
                                                        
                                     
                                                        
        """
        self.n_instance = n_instance
        self.n_items = n_items
        self.knapsack_capacity = knapsack_capacity

    def generate_instances(self):
        """
                                                    

                
                                                        
                                                   
                                                 
                                                              
        """
        np.random.seed(2024)                                
        instance_data = []

        for _ in range(self.n_instance):
                                                                                          
            item_weights = np.random.randint(10, self.knapsack_capacity / 2 + 10, size=self.n_items).tolist()

                                                                     
            item_values = np.random.randint(1, 101, size=self.n_items).tolist()                            

                                                                             
            instance_data.append((item_weights, item_values, self.knapsack_capacity))

        return instance_data
