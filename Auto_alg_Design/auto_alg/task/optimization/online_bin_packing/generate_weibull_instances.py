import numpy as np


def generate_weibull_dataset(num_instances, num_items, capacity_limit):
    np.random.seed(2024)

    dataset = {}

    for i in range(num_instances):
        instance = {
            'capacity': capacity_limit,
            'num_items': num_items,
            'items': []
        }

        items = []

                                                                  
        samples = np.random.weibull(3, num_items) * 45

                                                 
        samples = np.clip(samples, 1, capacity_limit)

                                                     
        sizes = np.round(samples).astype(int)

                                       
        for size in sizes:
            items.append(size)

        instance['items'] = np.array(items)

        if num_items not in dataset:
            dataset[f'instance_{i}'] = instance

    return dataset
