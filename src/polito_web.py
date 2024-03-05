import os
import re
import html
import time
import getpass
import requests
import urllib.parse
from bs4 import BeautifulSoup


class Link:
    codice = None
    anno = None
    is_elearn = False

    def __init__(self, code: str, year: str, is_elearn: bool):
        self.codice = code
        self.anno = year
        self.is_elearn = is_elearn

    def get_year(self):
        return self.anno

    def get_code(self):
        return self.codice

    def get_is_elearn(self):
        return self.is_elearn


class Corso:
    links = []
    nome = None
    periodo = None

    def __init__(self, nome: str, periodo: str):
        self.nome = nome
        self.periodo = periodo
        self.links = []

    def add_link(self, link):
        self.links.append(link)


class PolitoWeb:
    login_cookie = None
    dl_folder = None
    lista = []  # da definire vuota, non None!!
    mat_cookie = None
    lista_mat = None
    last_update_remote = None
    last_update_local = None
    MAX_RETRY = 3  # Numero massimo per i tentativi di login

    nome_file = "nomefile"

    headers = {"User-Agent": "python-requests"}
    base_url = "https://didattica.polito.it/pls/portal30/"
    handler_url = base_url + "sviluppo.filemgr.handler"
    get_process_url = base_url + "sviluppo.filemgr.get_process_amount"
    file_last_update = ".last_update"  # il punto serve a nasconderlo sui sistemi UNIX

    def set_dl_folder(self, dl_folder):
        if not os.path.isdir(dl_folder):
            print("La cartella {} non esiste! La creo...".format(dl_folder));
            os.mkdir(dl_folder)
            print("Cartella {} creata!".format(dl_folder))
        self.dl_folder = dl_folder
        print("Cartella di download impostata: {}".format(dl_folder))

    def login(self, username=None, password=None):
        if (username is None) and (password is None):
            user = input("Username: ")
            passw = getpass.getpass("Password: ")
        else:
            user = username
            passw = password

        print("Logging in...")

        with requests.session() as s:
            s.get('https://idp.polito.it/idp/x509mixed-login')
            r = s.post('https://idp.polito.it/idp/Authn/X509Mixed/UserPasswordLogin',
                       data={'j_username': user, 'j_password': passw})
            rls = html.unescape(re.findall('name="RelayState".*value="(.*)"', r.text))
            if len(rls) > 0:
                relaystate = rls[0]
            else:
                # log.error("Credenziali errate! Utente: %s", user)
                return False
            samlresponse = html.unescape(re.findall('name="SAMLResponse".*value="(.*)"', r.text)[0])
            s.post('https://www.polito.it/Shibboleth.sso/SAML2/POST',
                   data={'RelayState': relaystate, 'SAMLResponse': samlresponse})
            r = s.post('https://login.didattica.polito.it/secure/ShibLogin.php')
            relaystate = html.unescape(re.findall('name="RelayState".*value="(.*)"', r.text)[0])
            samlresponse = html.unescape(re.findall('name="SAMLResponse".*value="(.*)"', r.text)[0])
            r = s.post('https://login.didattica.polito.it/Shibboleth.sso/SAML2/POST',
                       data={'RelayState': relaystate, 'SAMLResponse': samlresponse})
            if r.url == "https://didattica.polito.it/pls/portal30/sviluppo.pagina_studente_2016.main":  # Login Successful
                login_cookie = s.cookies
            else:
                # log.critical("Qualcosa nel login non ha funzionato!")
                return False
        # se sono arrivato qui vuol dire che sono loggato
        self.login_cookie = login_cookie
        return True

    def crawl(self):
        """
        Questa funzione va a prendere le videolezioni dalla sezione materiale (primo/secondo/terzo anno)
        """
        with requests.session() as s:
            s.cookies = self.login_cookie
            # per arrivare a pagina_anni non specifico l'anno perché tanto mi serve solo i
            # link per primo/secondo/terzo anno
            pagina_anni = s.get("https://didattica.polito.it/portal/pls/portal/sviluppo.materiale.elenco?a=&t=E").text
            soup = BeautifulSoup(pagina_anni, "html.parser")
            tutti_gli_a = soup.find_all("a")

            periodo = 0
            nuovo_corso = None

            for a in tutti_gli_a:

                # encode e poi decode mi serve per renderla stringa e non StringSearchable (?) che mi
                # viene restituito da soup

                testo = str(a.contents[-1].encode("utf-8").decode("utf-8"))
                link = str(a.get("href").encode("utf-8").decode("utf-8"))
                is_elearn = False

                if a.get("onclick") is not None:
                    link = str(a.get("onclick").encode("utf-8").decode("utf-8"))
                    is_elearn = True

                # se trovo la parola anno nel link che sto considerando vuol dire che aumento l'anno in cui sono
                # se parto da 0: 1=primo anno, 2=secondo, 3=terzo, 4=magistrale
                if "anno" in testo or "Magistrale" in testo:
                    periodo += 1
                    continue

                titolo_corso = re.search("(.+ - .+) (\([0-9]+/[0-9]+\))", testo)
                anno_corso = re.search("\(([0-9]+/[0-9]+)\)", testo)
                codice_link = re.search("([0-9]+)", link)

                if titolo_corso and codice_link and anno_corso:
                    # pulisco il titolo del corso perché verrà usato come nome per una cartella quindi
                    # prendo solo i caratteri alfanumerici
                    titolo_corso = re.sub("'", "", titolo_corso.group(1))
                    titolo_corso = re.sub("[^\w \-()]", "_", titolo_corso)
                    anno_corso = anno_corso.group(1)
                    codice_link = codice_link.group(1)

                    nuovo_corso = Corso(titolo_corso, str(periodo))
                    nuovo_corso.add_link(Link(codice_link, anno_corso, is_elearn))
                    self.lista.append(nuovo_corso)

                # se trovo solo l'anno e non il titolo del corso aggiungo il link al nuovo_corso
                # che sarebbe il corso che sstavo considerando al passo precendete
                elif anno_corso and codice_link:
                    anno_corso = anno_corso.group(1)
                    codice_link = codice_link.group(1)
                    nuovo_corso.add_link(Link(codice_link, anno_corso, is_elearn))

        # for corso in self.lista:
        #    print(">>> " + corso.nome + " [" + corso.periodo + "]")
        #    for link in corso.links:
        #        print("\t" + link.anno + " - " + link.codice + (" @" if link.is_elearn else ""))

    def menu(self):
        opzione = 0
        while not 1 <= opzione <= 2:
            print(
                "Cosa si desidera fare?:\n"
                "\t[1] - Menù materiali\n"
                "\t[2] - Menù videolezioni\n"
                "Premere [Ctrl-D] per terminare"
            )
            opzione = int(input("Scegli l'opzione: "))
            match opzione:
                case 1:
                    self._menu_mat()
                case 2:
                    self._menu_videolez()
            self._clear()

    """
        === private functions ===
    """

    def _get_lista_mat(self):
        # riceve la lista della materie sulla pagina principale del portale
        with requests.session() as s:
            s.cookies = self.login_cookie
            hp = s.get(
                "https://didattica.polito.it/portal/page/portal/home/Studente",
                headers=self.headers,
            )
            self.lista_mat = re.findall(
                "cod_ins=(.+)&incarico=([0-9]+).+>(.+)[ ]*<", hp.text
            )

    def _select_mat(self, indice):
        """
        Seleziona la materia, imposta i cookie per la materia corrente in
        self.mat_cookie,  crea al cartella per ospirate i file scaricati e
        ricava le informazioni sul last_update sia local che remote
        :param indice: indice della materia nella lista (self.lista_mat)
        """

        nome_mat = self._purge_string(self.lista_mat[indice][2])
        cartella_da_creare = os.path.join(self.dl_folder, nome_mat)
        self._mkdir_if_not_exists(cartella_da_creare)

        with requests.session() as s:
            s.cookies = self.login_cookie
            s.get(
                "https://didattica.polito.it/pls/portal30/sviluppo.chiama_materia",
                params={
                    "cod_ins": self.lista_mat[indice][0],
                    "incarico": self.lista_mat[indice][1],
                },
                headers=self.headers,
            )
            self.mat_cookie = s.cookies
            self._get_path_content(cartella_da_creare, "/")

    def _get_path_content(self, cartella, path, code="0"):
        """
        Funzione principale che si occupa ricorsivamete di scaricare i file
        :param cartella: la cartella il cui si sta lavorando (non posso usare)
                         self.working_folse perché è una funzione riscorsiva
        :param path: il persorso online
        :param code: il codice della cartella in cui mi trovo online
        """

        with requests.session() as s:
            s.cookies = self.mat_cookie
            # se non specifico il codice vuole dire che sono nella cartella iniziale e quindi
            # non devo inviare l'attributo code altrimenti mi esce un risultato non valido (??)
            if code != "0":
                json_result = s.get(
                    self.handler_url,
                    params={"action": "list", "path": path, "code": code},
                    headers=self.headers,
                )
            else:
                json_result = s.get(
                    self.handler_url,
                    params={"action": "list", "path": path},
                    headers=self.headers,
                )

            contenuto = json_result.json()

            # per controllare gli aggiornamenti mi serve il codice della cartella
            # lo prendo dal parent code del primo elemento che mi capita
            if path == "/":
                if len(contenuto["result"]) == 0:
                    print("Nessun materiale disponibile per la materia selezionata!")
                    return
                else:
                    folder_code = contenuto["result"][0]["parent_code"]
                    self._need_to_update(cartella, folder_code)
                    self._save_update_file(cartella)

            for i in contenuto["result"]:
                if i["name"].startswith("ZZZZZ"):  # si tratta delle videolezioni
                    continue

                if i["type"] == "dir":
                    # creo la cartella su cui procedere ricorsivamente
                    name = self._purge_string(i["name"])  # pulizia dei caratteri
                    cartella_da_creare = os.path.join(cartella, name)

                    self._mkdir_if_not_exists(cartella_da_creare)
                    print("Cartella: " + name)
                    new_path = self._my_path_join(cartella_da_creare, name)

                    # procedo ricorsivamente
                    self._get_path_content(cartella_da_creare, new_path, i["code"])

                elif i["type"] == "file":
                    if not re.findall("\.(\w{1,4})", i[self.nome_file]):
                        # se non trovo un'estensione uso il nome del file normale
                        nome_del_file = i["nomefile"]
                        print(
                            "[ WARNING  ] Nessuna estensione trovata. Uso il nome originale!"
                        )
                    else:
                        nome_del_file = i[self.nome_file]

                    if self._need_to_update_this(cartella, nome_del_file, i["date"]):
                        # scarico il file
                        print("[ DOWNLOAD ] " + nome_del_file)
                        self._download_file(cartella, nome_del_file, path, i["code"])
                    else:
                        print("[    OK    ] " + nome_del_file)

    def _download_file(self, cartella, name, path, code):
        with requests.session() as s:
            s.cookies = self.mat_cookie
            file = s.get(
                self.handler_url,
                params={
                    "action": "download",
                    "path": (path + "/" + name),
                    "code": code,
                },
                allow_redirects=True,
                headers=self.headers,
            )
            if (
                "text/html" in file.headers["content-type"]
                and '<body onload="document.forms[0].submit()">' in file.text
            ):
                file = s.post(
                    "https://file.didattica.polito.it/Shibboleth.sso/SAML2/POST",
                    data={
                        "RelayState": html.unescape(
                            re.findall('name="RelayState".*value="(.*)"', file.text)[0]
                        ),
                        "SAMLResponse": html.unescape(
                            re.findall('name="SAMLResponse".*value="(.*)"', file.text)[
                                0
                            ]
                        ),
                    },
                    allow_redirects=True,
                    headers=self.headers,
                )
            try:
                name = self._purge_string(name)
                open(os.path.join(cartella, name), "wb").write(file.content)
            except ValueError:
                # nel caso in cui non si riuscisse a salvere il file
                # si pulisce meglio il nome
                name = self._purge_string(name, "strong")
                open(os.path.join(cartella, name), "wb").write(file.content)

    def _menu_mat(self):
        # se non ho ancora salvato la lista delle materie per questa sessione
        # la salvo il self.lista_mat
        if self.lista_mat is None:
            self._get_lista_mat()

        i = 1
        print("\nElenco del materiale disponibile - (CTRL+D per terminare)")
        for mat in self.lista_mat:
            print("[%.2d] %s" % (i, mat[2]))
            i += 1
        print("(Il download verrà effettuato nella cartella: " + self.dl_folder + ")")
        x = -1
        while x not in range(1, i):
            try:
                x = input("Materia: ")
            except EOFError:
                print()
                return False  # Exit from while cycle of self.main()
            if x.isnumeric():
                x = int(x)
            else:
                continue

        self._select_mat(x - 1)

        print("--- Fine! ---     premi INVIO")
        input()
        return True
    
    def _last_update_remote(self, folder_code):
        """
        imposta self.last_update_remote
        :param folder_code: codice della cartella online
        """
        with requests.session() as s:
            s.cookies = self.mat_cookie
            json_result = s.get(self.get_process_url, params={"items": folder_code})
            if json_result:
                json_result = json_result.json()
                self.last_update_remote = json_result["result"]["lastUpload"]
            else:
                print("Impossibile stabilire la data dell'ultimo aggiornamento")
                self.last_update_remote = None

    def _last_update_local(self, cartella):
        """
        imposta self.last_update_local
        :param cartella: la cartella in cui sto lavorando
        """

        file_da_controllare_nt = os.path.join(
            *[self.dl_folder, cartella, self.file_last_update]
        )

        if os.path.isfile(file_da_controllare_nt):
            with open(file_da_controllare_nt, "r") as f:
                self.last_update_local = f.read()
        else:
            self.last_update_local = None

    def _need_to_update(self, cartella, folder_code):
        self._last_update_local(cartella)
        self._last_update_remote(folder_code)
        if self.last_update_local is not None and self.last_update_remote is not None:
            if self.last_update_local < self.last_update_remote:
                return True
            else:
                return False
        else:
            return True  # se non trovo niente è come se dovessi aggiornare tutto

    def _save_update_file(self, cartella):
        """
        salva il file per tenere traccia dell'ultimo aggiornamento
        :return:
        """

        # se il file esiste già bisogna usa 'r+' e non 'w' per motivi
        # di windows di operazioni su file nascosti
        update_file = os.path.join(*[self.dl_folder, cartella, self.file_last_update])

        mode = "r+" if os.path.isfile(update_file) else "w"

        with open(update_file, mode) as f:
            f.write(self.last_update_remote)

        # nascondo il file se sono su windows se l'ho creato per la prima volta (modo 'w')
        if os.name == "nt" and mode == "w":
            self._hide_file_in_win32(update_file)

    def _need_to_update_this(self, cartella, nomefile, data):
        """
        Restituiisce vero nel caso in cui il file è più aggiornato
        rispetto alla versione locale o in caso il file non
        ci sia prorpio nella versione locale. Per la versione locale
        controlla sia con _purge_string che con _purge_string_strong
        :param data: la data del file che sto considerando
        :return: bool
        """

        nomefile = self._purge_string(nomefile)
        file_da_controllare = os.path.join(*[self.dl_folder, cartella, nomefile])

        if not os.path.isfile(file_da_controllare):
            nomefile = self._purge_string(nomefile, "strong")
            file_da_controllare = os.path.join(*[self.dl_folder, cartella, nomefile])
            if not os.path.isfile(file_da_controllare):
                return True

        if self.last_update_local is None:
            return True

        if self.last_update_local < data:
            return True

        return False


    def _menu_videolez(self):

        periodo = 0

        print("[1] - Primo anno")
        print("[2] - Secondo anno")
        print("[3] - Terzo anno")
        print("[4] - Magistrale")

        while not 1 <= periodo <= 4:
            periodo = int(input("Scegli l'anno: "))

        # conversione a stringa per comodità
        periodo = str(periodo)

        # creo una lista dei corsi che l'utente seleziona per aiutarmi successivamente
        lista_corsi_selezionati = []
        for corso in self.lista:
            if corso.periodo == periodo:
                lista_corsi_selezionati.append(corso)
                print("[{:>2}] - {}".format(len(lista_corsi_selezionati), corso.nome))

        n_corso_scelto = 0
        while not 1 <= n_corso_scelto <= len(lista_corsi_selezionati):
            n_corso_scelto = int(input("Scegli il corso: "))

        # importante -1 perché sono indici di un vettore
        corso_scelto = lista_corsi_selezionati[n_corso_scelto - 1]
        print(corso_scelto.nome)

        for link in corso_scelto.links:
            print("[{}] - {}".format(corso_scelto.links.index(link) + 1, link.anno))

        n_link_scelto = 0
        while not 1 <= n_link_scelto <= len(corso_scelto.links):
            n_link_scelto = int(input("Scegli l'anno delle videolezioni: "))

        # importante il -1 come sopra...
        link_scelto = corso_scelto.links[n_link_scelto - 1]

        # chiedo all'utente se vuole mantenere aggiornate le videolezioni
        update = ""
        while not (update == "s" or update == "n"):
            update = input("Mantenere la materia aggiornata all'ultima videolezione? [s/n] ")
        update = (True if update == "s" else False)  # update diventa bool

        # se non c'è crea la cartella per ospitare la videolezione
        nome_cartella_corso = self.__generate_folder_name(corso_scelto, link_scelto, update)
        if not os.path.isdir(os.path.join(self.dl_folder, nome_cartella_corso)):
            os.mkdir(os.path.join(self.dl_folder, nome_cartella_corso))
        # scarica le videolezioni

        self.__download_video(link_scelto, nome_cartella_corso)
        return 1

    # funzione che ricerca tutte le cartelle che hanno un numero tra parentesi
    # che sarebbe l'id del corso (nome della cartella specificato da __generate_folder_name)
    # se le trova e ci sono nuove videolezioni procede a scaricarle
    def check_for_updates(self):
        for folder_name in os.listdir(self.dl_folder):
            if folder_name.endswith("noupdate"):
                continue

            link = self.__decode_folder_name(folder_name)
            # se non riesco a decodificare la cartella, continuo
            if link is None:
                continue

            if link is not None:
                ultima = int(self.__find_last_video_number(folder_name))  # ultima videolezione nella cartella
                links = self.__extract_video_links(link)
                quante_videolezioni = len(links)  # numero di videolezioni online
                if quante_videolezioni == ultima:
                    continue  # mi fermo qui

                print("Ci sono {} nuove videolezioni per {}!".format(quante_videolezioni - ultima,  folder_name))
                lezioni_da_scaricare = [ultima + 1, quante_videolezioni]  # "range" delle videolezioni da scaricare
                self.__download_video(link, folder_name, lezioni_da_scaricare)

    @staticmethod
    def bell():
        print(chr(7))
        time.sleep(1)

    # -------------- #
    # classi private #
    # -------------- #

    # trova il numero dell'ultima lezione scaricata nella cartella
    # @return integer
    def __find_last_video_number(self, cartella):
        cartella = os.path.join(self.dl_folder, cartella)
        ultimo_video = sorted(os.listdir(cartella))[-1]  # l'ultimo video in ordine alfabetico
        ultimo_numero = re.search(".?([0-9]+).?", ultimo_video)
        if ultimo_numero:
            return ultimo_numero.group(1)
        else:
            print("Non ho trovato nessun video. La cartella è forse vuota (?)")
            return 0

    def __generate_video_url(self, link: Link):
        base_url = "https://didattica.polito.it/portal/pls/portal/sviluppo.videolezioni.vis?cor="
        base_url_e = "https://elearning.polito.it/gadgets/video/template_video.php?"
        url = "<ERRORE NELLA GENERAZIONE URL>"
        if not link.is_elearn:
            url = base_url + link.codice
        else:
            with requests.session() as s:
                s.cookies = self.login_cookie
                data = s.get("https://didattica.polito.it/pls/portal30/sviluppo.materiale.json_dokeos_par?inc=" +
                             link.codice).json()
                url = base_url_e + urllib.parse.urlencode(data)
        # print(url)
        return url

    @staticmethod
    def __generate_folder_name(corso: Corso, link: Link, update):
        suffix = ("" if update else " - noupdate")
        codice = (link.codice if not link.is_elearn else "E_" + link.codice)
        return "{} ({}) [{}]{}".format(corso.nome, link.anno.replace("/", "-"), codice, suffix)

    @staticmethod
    def __decode_folder_name(folder_name: str):
        codice = re.search("\[([E_\d]+)\]", folder_name)
        anno = re.search("\((\d+-\d+)\)", folder_name)

        codice = codice.group(1) if codice else None
        anno = anno.group(1) if anno else None

        if codice is None:
            return None
        else:
            is_elearn = True if codice.startswith("E_") else False
            return Link(re.sub("E_", "", codice), anno, is_elearn)

    # @param inp = [start, end]
    def __download_video(self, link: Link, nome_cartella_corso, inp=None):
        print("Sto cercando le videolezioni...")
        links = self.__extract_video_links(link)
        quante_videolezioni = len(links)

        # mi serve passarlo come parametro dalla funzione checkForUpdates
        if inp is None:
            print(str(quante_videolezioni) + " videolezioni trovate!")
            print("Quali videolezioni vuoi scaricare? Inserisci un range o un numero...")
            print("(Per esempio per scaricarle tutte scrivi: 1-" + str(len(links)) + ")")
            inp = input("Lezioni: ").split("-")

        if len(inp) > 0:
            st = int(inp[0])
            end = (int(inp[1]) if len(inp) == 2 else int(inp[0]))
            for i in range(st, end + 1):
                url = self.__extract_download_url(links[i - 1])
                self.__download_single_video(url, nome_cartella_corso)
            print("--- Done! ---")
            self.bell()
        else:
            print("Riprova")

    def __extract_video_links(self, link: Link):
        url = self.__generate_video_url(link)

        with requests.session() as s:
            s.cookies = self.login_cookie
            r = s.get(url)

            if "didattica.polito.it" in url:
                links = re.findall('href="(sviluppo\.videolezioni\.vis.*lez=\w*)">', r.text)
                for i in range(len(links)):
                    links[i] = 'https://didattica.polito.it/pls/portal30/' + html.unescape(links[i])
            elif "elearning.polito.it" in url:
                links = re.findall("href='(template_video\.php\?[^']*)", r.text)
                for i in range(len(links)):
                    links[i] = 'https://elearning.polito.it/gadgets/video/' + html.unescape(links[i])
            else:
                print("Impossibile trovare le videolezioni")
                return 0
            return links

    def __ready(self):
        if (
                self.login_cookie is None or
                self.dl_folder is None
        ):
            # log.critical("Sessione non pronta!")
            return 0
        else:
            return 1

    def __download_single_video(self, url, nome_cartella_corso):
        filename = url.split('/')[-1]
        print('Scaricando "' + filename + '"...')
        with requests.session() as s:
            f = s.get(url)
            open(os.path.join(*[self.dl_folder, nome_cartella_corso, filename]), 'wb').write(f.content)

    def __extract_download_url(self, url):
        with requests.session() as s:
            s.cookies = self.login_cookie
            r = s.get(url)
            if "didattica.polito.it" in url:
                d_url = re.findall('href="(.*)".*Video', r.text)[0]
                r = s.get('https://didattica.polito.it' + html.unescape(d_url), allow_redirects=False)
                d_url = r.headers['location']
            elif "elearning.polito.it" in url:
                d_url = re.findall('href="(download.php[^\"]*).*video1', r.text)[0]
                r = s.get('https://elearning.polito.it/gadgets/video/' + html.unescape(d_url), allow_redirects=False)
                d_url = r.headers['location']
            else:
                print("Impossibile trovare i file da scaricare")
                d_url = None
                exit()
        return d_url

    """
        === static methods ===
    """

    @staticmethod
    def _my_path_join(a, b):
        if a.endswith("/"):
            return a + b
        else:
            return a + "/" + b

    def _purge_string(self, a, strong=None):
        if strong is None:
            return re.sub('[/:*?"<>|]', "", a).strip()
        elif strong == "strong":
            # se è presente l'attributo strong faccio il purge_string
            # leggero e poi quello strong
            return re.sub("[^a-zA-Z0-9 .]", "", self._purge_string(a)).strip()
        else:
            return a

    @staticmethod
    def _mkdir_if_not_exists(folder):
        if not os.path.isdir(folder):
            os.mkdir(folder)

    @staticmethod
    def _clear():
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def _hide_file_in_win32(file_da_nascondere):
        """
        Funzione che permette di nascondere un file su windows
        in particolare quello del last_update
        :param file_da_nascondere: path del file na nascondere
        """
        try:
            subprocess.call(["attrib", "+H", file_da_nascondere])
        except ValueError:
            print("[  ERRORE  ] Impossibile nascondere il file di timestamp")
