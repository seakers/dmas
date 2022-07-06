import pandas as pd
import matplotlib.pyplot as plt


def plot_power_state(results_dir, n_agents):
    if n_agents < 1:
        return
    elif n_agents < 2:
        figure, axis = plt.subplots(5, 1)

        df = pd.read_csv(results_dir + f'A0_state.csv')

        axis[0].step(df['t'], df['p_in'])
        axis[0].set_title("Power Generated [W]")
        axis[0].grid(True)

        axis[1].step(df['t'], df['p_out'])
        axis[1].set_title("Power Consumed [W]")
        axis[1].grid(True)

        axis[2].step(df['t'], df['p_tot'])
        axis[2].set_title("Total Power ")
        axis[2].grid(True)

        axis[3].step(df['t'], df['p_in'])
        axis[3].step(df['t'], -df['p_out'])
        axis[3].step(df['t'], df['p_tot'])
        axis[3].set_title("Total Power ")
        axis[3].grid(True)

        axis[4].plot(df['t'], df['e_str'] / df['e_cap'])
        axis[4].set_title("Battery Charge")
        axis[4].grid(True)

        plt.subplots_adjust(wspace=0.4,
                            hspace=0.9)
        plt.show()
    else:
        figure, axis = plt.subplots(5, n_agents)

        for i in range(n_agents):
            df = pd.read_csv(results_dir + f'A{i}_state.csv')

            axis[0][i].step(df['t'], df['p_in'])
            axis[0][i].set_title("Power Generated [W]")
            axis[0][i].grid(True)

            axis[1][i].step(df['t'], df['p_out'])
            axis[1][i].set_title("Power Consumed [W]")
            axis[1][i].grid(True)

            axis[2][i].step(df['t'], df['p_tot'])
            axis[2][i].set_title("Total Power ")
            axis[2][i].grid(True)

            axis[3][i].step(df['t'], df['p_in'])
            axis[3][i].step(df['t'], -df['p_out'])
            axis[3][i].step(df['t'], df['p_tot'])
            axis[3][i].set_title("Total Power ")
            axis[3][i].grid(True)

            axis[4][i].plot(df['t'], df['e_str'] / df['e_cap'])
            axis[4][i].set_title("Battery Charge")
            axis[4][i].grid(True)

        plt.subplots_adjust(wspace=0.4,
                            hspace=0.9)
        plt.show()


def plot_data_rate_state(results_dir, n_agents):
    if n_agents < 1:
        return
    elif n_agents < 2:
        figure, axis = plt.subplots(4, 1)

        df = pd.read_csv(results_dir + f'A0_state.csv')

        axis[0].step(df['t'], df['r_in'])
        axis[0].set_title("Data-rate In [Mbps]")
        axis[0].grid(True)

        axis[1].step(df['t'], df['r_out'])
        axis[1].set_title("Data-rate Out [Mbps]")
        axis[1].grid(True)

        axis[2].step(df['t'], df['r_tot'])
        axis[2].set_title("Data-rate Total [Mbps]")
        axis[2].grid(True)

        axis[3].step(df['t'], df['r_in'])
        axis[3].step(df['t'], -df['r_out'])
        axis[3].step(df['t'], df['r_tot'])
        axis[3].set_title("Data-rate")
        axis[3].grid(True)

        plt.subplots_adjust(wspace=0.4,
                            hspace=0.9)
        plt.show()
    else:
        figure, axis = plt.subplots(4, n_agents)

        for i in range(n_agents):
            df = pd.read_csv(results_dir + f'A{i}_state.csv')

            axis[0][i].step(df['t'], df['r_in'])
            axis[0][i].set_title("Data-rate In [Mbps]")
            axis[0][i].grid(True)

            axis[1][i].step(df['t'], df['r_out'])
            axis[1][i].set_title("Data-rate Out [Mbps]")
            axis[1][i].grid(True)

            axis[2][i].step(df['t'], df['r_tot'])
            axis[2][i].set_title("Data-rate Total [Mbps]")
            axis[2][i].grid(True)

            axis[3][i].step(df['t'], df['r_in'])
            axis[3][i].step(df['t'], -df['r_out'])
            axis[3][i].step(df['t'], df['r_tot'])
            axis[3][i].set_title("Data-rate")
            axis[3][i].grid(True)

        plt.subplots_adjust(wspace=0.4,
                            hspace=0.9)
        plt.show()


def plot_data_state(results_dir, n_agents):
    if n_agents < 1:
        return
    elif n_agents < 2:
        figure, axis = plt.subplots(3, 1)

        df = pd.read_csv(results_dir + f'A0_state.csv')

        axis[0].plot(df['t'], df['d_in'] / df['d_in_cap'])
        axis[0].set_title("Incoming Buffer State [%]")
        axis[0].grid(True)

        axis[1].plot(df['t'], df['d_out'] / df['d_out_cap'])
        axis[1].set_title("Outgoing Buffer State [%]")
        axis[1].grid(True)

        axis[2].plot(df['t'], df['d_mem'] / df['d_mem_cap'])
        axis[2].set_title("Internal Memory State [%]")
        axis[2].grid(True)

        plt.subplots_adjust(wspace=0.4,
                            hspace=0.9)
        plt.show()
    else:
        figure, axis = plt.subplots(3, n_agents)

        for i in range(n_agents):
            df = pd.read_csv(results_dir + f'A{i}_state.csv')

            axis[0][i].plot(df['t'], df['d_in'] / df['d_in_cap'])
            axis[0][i].set_title("Incoming Buffer State [%]")
            axis[0][i].grid(True)

            axis[1][i].plot(df['t'], df['d_out'] / df['d_out_cap'])
            axis[1][i].set_title("Outgoing Buffer State [%]")
            axis[1][i].grid(True)

            axis[2][i].plot(df['t'], df['d_mem'] / df['d_mem_cap'])
            axis[2][i].set_title("Internal Memory State [%]")
            axis[2][i].grid(True)

        plt.subplots_adjust(wspace=0.4,
                            hspace=0.9)
        plt.show()
