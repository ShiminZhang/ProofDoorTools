import matplotlib.pyplot as plt

def init_plot(x_label, y_label, title):
    plt.figure(figsize=(10, 6))
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    plt.title(title)
    

def draw_scaling_plot_line(x,y,label):
    """
    Draw a scaling plot from the given data.

    Args:
    """
    zipped_data = list(zip(x, y))
    zipped_data.sort(key=lambda x: x[0])
    x, y = zip(*zipped_data)
    plt.plot(x, y, linestyle="-", label=label)

def finish_plot(output_path):
    plt.legend()
    plt.savefig(output_path)

def draw_cactus_plot(data, x_label, y_label, title, output_path):
    """
    Draw a cactus plot from the given data.
    """
    pass

if __name__ == "__main__":
    data = {
        "n": [10, 20, 30, 40, 50],
        "time": [1.2, 2.3, 3.4, 4.5, 5.6]
    }
    draw_scaling_plot(data, "n", "time", "Scaling Plot", "test.png")
