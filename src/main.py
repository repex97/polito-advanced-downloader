import os
import argparse
from polito_web import PolitoWeb


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


if __name__ == "__main__":
    # command parser
    parser = argparse.ArgumentParser(description="Script Python per scaricare e tenere aggiornate le videolezioni\ndel \
    Politecnico di Torino.", add_help=True)
    parser.add_argument("-u", "--update-only", action="store_true", default=False,
                        help="Aggiorna le videolezioni ed esce")
    args = parser.parse_args()
    # end command parser

    sess = PolitoWeb()
    sess.set_dl_folder("C:\\video_lezioni")

    print("PoliTo Advanced Downloader - v 0.2.0", end="\n\n")

    print("Credenziali di accesso per http://didattica.polito.it")
    # si può usare sess.login('il_tuo_user', 'la_tua_password') per evitare di dover fare il login ogni votla
    while not sess.login():
        print("Impossibile effettuare il login, riprovare!")

    if args.update_only:  # se dovevo solo cercare gli aggiornamenti mi fermo qui
        sess.check_for_updates()
        sess.bell()
        exit(0)

    sess.crawl()
    while sess.menu():
        clear()
