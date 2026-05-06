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

(defn- upload-form []
  (let [form (r/atom {:quarter 1 :year 2026 :file nil})]
    (fn [{:keys [on-file kind]}]
      [:div {:style {:display "flex" :flex-direction "column" :gap "20px"}}
       [:div {:style {:display "flex" :gap "12px"}}
        [:div {:style {:width "150px"}}
         [inputs/select
          {:label "Trimestre"
           :value (str (:quarter @form))
           :options [{:value "1" :label "Q1"} {:value "2" :label "Q2"}
                     {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
           :on-change #(swap! form assoc :quarter (js/parseInt %))}]]
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
                                    (on-file f (:quarter @form) (:year @form))))))}]
        [layout/icon "upload" {:width 36 :height 36}]
        [:strong "Solte os arquivos aqui ou clique para selecionar"]
        [:p {:style {:font-size "12px" :max-width "340px"}}
         (case kind
           :perks "Aceitamos XLSX com Cliente Pipo, Valor, Mês (Competência) e Ano. Re-upload substitui os subsídios existentes do trimestre."
           "Aceitamos CSV, XLSX, PDF (NFs). Máx. 50MB por arquivo. Os campos serão validados antes do processamento.")]
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
          [:div.card-sub "Planilha \"Consulta - Follow up Faturamento\". Re-upload do mesmo trimestre substitui as linhas existentes (exceto se a apuração já estiver Locked)."]]
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
            :on-file (fn [f q y] (rf/dispatch [:revops/upload-financial f q y]))}])]

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
          [:div.callout {:style {:border-color "var(--success-light)"
                                 :background "var(--success-lightest)"}}
           [layout/icon "check" {:width 20 :height 20}]
           [:div {:style {:flex 1}}
            [:strong (str "Subsídios aplicados: "
                          (count (or (:items perk-result) [])) " clientes")]]]

          :else
          [upload-form
           {:kind :perks
            :on-file (fn [f q y] (rf/dispatch [:revops/upload-perks f q y]))}])]])))
