class Config:
    def __init__(self, use_xyz, tome, num_points, num_class, input_dim, init_hidden_dim, k):
        self.use_xyz = use_xyz
        self.tome = tome
        self.num_points = num_points
        self.num_class = num_class
        self.input_dim = input_dim
        self.init_hidden_dim = init_hidden_dim
        self.k = k