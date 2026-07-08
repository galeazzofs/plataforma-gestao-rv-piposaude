(ns app.views.revops.financial-upload
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.inputs :as inputs]
            [app.auth.subs]))

;; Upload Financeiro — design's dropzone + history table.

(defn- upload-result-stats [result]
  (let [stats (or (:stats result) {})]
    [:div.callout {:style {:border-color "var(--success-light)" :background "var(--success-lightest)"}}
     [layout/icon "check" {:width 20 :height 20}]
     [:div {:style {:flex 1}}
      [:strong (str "Upload concluído: " (or (:rows_persisted result) 0) " linhas persistidas")]
      [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
       (str/join " · "
                 (for [[k label] [[:total_lidas "lidas"] [:persistidas "persistidas"]
                                  [:descartadas_status "status ≠ RECEBIDO"]
                                  [:descartadas_periodo "fora do período"]
                                  [:descartadas_vazias "vazias"]]
                       :let [v (get stats k 0)]
                       :when (some? v)]
                   (str (or v 0) " " label)))]]]))

(defn- perk-result-stats [result]
  (let [stats           (or (:stats result) {})
        matched-clients (or (:matched_clients result) 0)
        matched-rows    (or (:matched result) 0)
        missed          (or (:missed result) 0)
        skipped-locked  (or (:skipped_locked result) 0)
        missed-clients  (or (:missed_clients result) [])]
    [:div.callout {:style {:border-color "var(--success-light)"
                           :background "var(--success-lightest)"}}
     [layout/icon "check" {:width 20 :height 20}]
     [:div {:style {:flex 1}}
      [:strong (str "Subsídios aplicados: " matched-clients " clientes")]
      [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
       (str/join " · "
                 [(str matched-rows " linhas aplicadas")
                  (str missed " sem cliente cadastrado")
                  (str skipped-locked " em meses locked preservados")
                  (str (or (:total_lidas stats) 0) " lidas")
                  (str (or (:descartadas_periodo stats) 0) " fora do período")
                  (str (or (:descartadas_vazias stats) 0) " vazias")])]
      (when (seq missed-clients)
        [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
         (str "Clientes não encontrados: "
              (str/join ", " (take 8 missed-clients))
              (when (> (count missed-clients) 8)
                (str " +" (- (count missed-clients) 8))))])]]))

(defn- upload-form []
  (let [form (r/atom {:year 2026 :file nil})]
    (fn [{:keys [on-file kind]}]
      [:div {:style {:display "flex" :flex-direction "column" :gap "20px"}}
       [:div {:style {:display "flex" :gap "12px"}}
        [:div {:style {:width "150px"}}
         [inputs/select
          {:label "Ano"
           :value (str (:year @form))
           :options [{:value "2024" :label "2024"} {:value "2025" :label "2025"}
                     {:value "2026" :label "2026"} {:value "2027" :label "2027"}]
           :on-change #(swap! form assoc :year (js/parseInt %))}]]]

       [:label.dropzone
        [:input {:type "file"
                 :accept ".xlsx,.xls,.csv"
                 :style {:display "none"}
                 :on-change (fn [e]
                              (let [f (-> e .-target .-files (aget 0))]
                                (when f
                                  (swap! form assoc :file f)
                                  (when on-file
                                    (on-file f (:year @form))))))}]
        [layout/icon "upload" {:width 36 :height 36}]
        [:strong "Solte os arquivos aqui ou clique para selecionar"]
        [:p {:style {:font-size "12px" :max-width "340px"}}
         (case kind
           :perks "Aceitamos CSV ou XLSX com Cliente Pipo, Valor, Mês (Competência) e Ano (formato BR ou US). Cada linha entra no seu próprio mês; re-upload atualiza os meses abertos do ano."
           "Aceitamos CSV, XLSX, PDF (NFs). Cada NF entra no seu próprio mês de recebimento. Máx. 50MB por arquivo.")]
        [:button.btn.btn-primary.btn-sm {:style {:margin-top "8px"}}
         "Selecionar arquivos"]]])))

(defn financial-upload-page []
  (fn []
    (let [result        @(rf/subscribe [:revops/upload-result])
          loading?      @(rf/subscribe [:revops/upload-loading?])
          perk-result   @(rf/subscribe [:revops/perk-upload-result])
          perk-loading? @(rf/subscribe [:revops/perk-upload-loading?])
          user          @(rf/subscribe [:auth/current-user])
          route         @(rf/subscribe [:current-route-name])]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "operação" "upload financeiro"]
        :title "Upload Financeiro"
        :subtitle "NFs e subsídios em XLSX"
        :header-actions nil}

       ;; Faturamento
       [:div.card
        [:div.card-head
         [:div [:h3 "Faturamento"]
          [:div.card-sub "Planilha \"Consulta - Follow up Faturamento\". Cada NF entra no mês da sua data de recebimento. Re-upload do mesmo ano atualiza os meses abertos e preserva os meses já fechados (Locked)."]]
         (when result
           [:button.btn.btn-secondary.btn-sm
            {:on-click #(rf/dispatch [:revops/upload-reset])}
            "Novo upload"])]
        (cond
          loading?
          [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"
                         :font-family "var(--font-mono)" :font-size "12px"}}
           "Processando arquivo…"]

          result
          [upload-result-stats result]

          :else
          [upload-form
           {:kind :financial
            :on-file (fn [f y] (rf/dispatch [:revops/upload-financial f y]))}])]

       ;; Subsídios / Perks
       [:div.card
        [:div.card-head
         [:div [:h3 "Subsídios / Perks"]
          [:div.card-sub "Planilha de subsídios: soma por cliente e desconta das NFs na apuração."]]
         (when perk-result
           [:button.btn.btn-secondary.btn-sm
            {:on-click #(rf/dispatch [:revops/perk-upload-reset])}
            "Novo upload"])]
        (cond
          perk-loading?
          [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"
                         :font-family "var(--font-mono)" :font-size "12px"}}
           "Processando subsídios…"]

          perk-result
          [perk-result-stats perk-result]

          :else
          [upload-form
           {:kind :perks
            :on-file (fn [f y] (rf/dispatch [:revops/upload-perks f y]))}])]])))
