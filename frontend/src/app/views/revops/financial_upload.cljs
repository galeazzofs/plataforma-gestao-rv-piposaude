(ns app.views.revops.financial-upload
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn upload-form []
  (let [form (r/atom {:quarter 1 :year 2026 :file nil})]
    (fn []
      [:div {:style {:display "flex" :flex-direction "column" :gap "20px"}}
       [:div {:style {:display "flex" :gap "16px" :padding "16px"
                      :background t/beige-100
                      :border-radius (:md t/border-radius)
                      :align-items "flex-start"}}
        [:span {:style {:font-size "20px"}} [:span {:aria-hidden "true"} "ℹ️"]]
        [:div {:style {:flex 1}}
         [:p {:style {:color t/text-primary :margin "0 0 8px 0"
                      :font-size (:sm t/font-sizes)
                      :line-height "1.6"}}
          "Faça upload do arquivo XLSX no formato \"Consulta - Follow up Faturamento\". "
          "O sistema vai detectar os cabeçalhos automaticamente."]
         [:p {:style {:color t/text-secondary :margin "0"
                      :font-size (:xs t/font-sizes)
                      :line-height "1.5"}}
          "Filtros aplicados: status RECEBIDO, dentro do trimestre escolhido, "
          "Cliente \"Mãe\" e NF Líquido preenchidos. "
          "Re-upload do mesmo trimestre substitui as linhas existentes "
          "(salvo se a apuração já estiver LOCKED)."]]]

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
           :options [{:value "2024" :label "2024"}
                     {:value "2025" :label "2025"}
                     {:value "2026" :label "2026"}
                     {:value "2027" :label "2027"}]
           :on-change #(swap! form assoc :year (js/parseInt %))}]]]

       [inputs/file-upload
        {:label "Arquivo Financeiro (.xlsx)"
         :accept ".xlsx,.xls"
         :on-file (fn [file]
                    (swap! form assoc :file file)
                    (rf/dispatch [:revops/upload-financial
                                  file
                                  (:quarter @form)
                                  (:year @form)]))}]])))

(defn result-view [result]
  (let [stats (:stats result)]
    [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
     [:div {:style {:padding "16px" :background t/success-light
                    :border-radius (:md t/border-radius)
                    :color t/success-dark}}
      [:strong (str "✅ Upload concluído — "
                    (:rows_persisted result) " linhas persistidas")]]

     [:div {:style {:display "grid"
                    :grid-template-columns "repeat(5, 1fr)"
                    :gap "12px"}}
      [:div {:style {:padding "12px" :background t/bg-card
                     :border-radius (:md t/border-radius)
                     :border (str "1px solid " t/border-default)}}
       [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
        "Total lidas"]
       [:div {:style {:font-size (:lg t/font-sizes)
                      :font-weight (:semibold t/font-weights)}}
        (str (:total_lidas stats 0))]]
      [:div {:style {:padding "12px" :background t/bg-card
                     :border-radius (:md t/border-radius)
                     :border (str "1px solid " t/border-default)}}
       [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
        "Persistidas"]
       [:div {:style {:font-size (:lg t/font-sizes)
                      :font-weight (:semibold t/font-weights)
                      :color t/success-default}}
        (str (:persistidas stats 0))]]
      [:div {:style {:padding "12px" :background t/bg-card
                     :border-radius (:md t/border-radius)
                     :border (str "1px solid " t/border-default)}}
       [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
        "Status ≠ RECEBIDO"]
       [:div {:style {:font-size (:lg t/font-sizes)}}
        (str (:descartadas_status stats 0))]]
      [:div {:style {:padding "12px" :background t/bg-card
                     :border-radius (:md t/border-radius)
                     :border (str "1px solid " t/border-default)}}
       [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
        "Fora do período"]
       [:div {:style {:font-size (:lg t/font-sizes)}}
        (str (:descartadas_periodo stats 0))]]
      [:div {:style {:padding "12px" :background t/bg-card
                     :border-radius (:md t/border-radius)
                     :border (str "1px solid " t/border-default)}}
       [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
        "Vazias / inválidas"]
       [:div {:style {:font-size (:lg t/font-sizes)}}
        (str (:descartadas_vazias stats 0))]]]

     [:div {:style {:padding "12px" :background t/bg-main
                    :border-radius (:md t/border-radius)
                    :font-size (:sm t/font-sizes)
                    :color t/text-secondary}}
      "Próximo passo: vá para "
      [:strong "Apuração"]
      " e clique em ▶ Iniciar Cálculo. "
      "O sistema vai matchear as NFs com as Apólices e gerar as comissões."]

     [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
      [btn/button {:variant :secondary
                   :on-click #(rf/dispatch [:revops/upload-reset])}
       "Novo Upload"]
      [btn/button {:variant :primary
                   :on-click #(rf/dispatch [:navigate! :revops/appraisal])}
       "Ir para Apuração →"]]]))

(defn perk-upload-form []
  (let [form (r/atom {:quarter 1 :year 2026 :file nil})]
    (fn []
      [:div {:style {:display "flex" :flex-direction "column" :gap "20px"}}
       [:div {:style {:display "flex" :gap "16px" :padding "16px"
                      :background t/beige-100
                      :border-radius (:md t/border-radius)
                      :align-items "flex-start"}}
        [:span {:style {:font-size "20px"}} [:span {:aria-hidden "true"} "ℹ️"]]
        [:div {:style {:flex 1}}
         [:p {:style {:color t/text-primary :margin "0 0 8px 0"
                      :font-size (:sm t/font-sizes)
                      :line-height "1.6"}}
          "Faça upload da planilha de subsídios/perks. "
          "O sistema vai detectar as colunas \"Cliente Pipo\", \"Valor\", "
          "\"Mês (Competência)\" e \"Ano\" automaticamente."]
         [:p {:style {:color t/text-secondary :margin "0"
                      :font-size (:xs t/font-sizes)
                      :line-height "1.5"}}
          "Os subsídios serão somados por cliente e subtraídos do total "
          "de NFs na apuração. Re-upload substitui os subsídios existentes "
          "do trimestre."]]]

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
           :options [{:value "2024" :label "2024"}
                     {:value "2025" :label "2025"}
                     {:value "2026" :label "2026"}
                     {:value "2027" :label "2027"}]
           :on-change #(swap! form assoc :year (js/parseInt %))}]]]

       [inputs/file-upload
        {:label "Planilha de Subsídios (.xlsx)"
         :accept ".xlsx,.xls"
         :on-file (fn [file]
                    (swap! form assoc :file file)
                    (rf/dispatch [:revops/upload-perks
                                  file
                                  (:quarter @form)
                                  (:year @form)]))}]])))

(defn perk-result-view [result]
  (let [stats (:stats result)]
    [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
     [:div {:style {:padding "16px" :background t/success-light
                    :border-radius (:md t/border-radius)
                    :color t/success-dark}}
      [:strong (str "✅ Upload de subsídios concluído — "
                    (:matched result) " matched, "
                    (:missed result) " missed")]]

     [:div {:style {:display "grid"
                    :grid-template-columns "repeat(4, 1fr)"
                    :gap "12px"}}
      [:div {:style {:padding "12px" :background t/bg-card
                     :border-radius (:md t/border-radius)
                     :border (str "1px solid " t/border-default)}}
       [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
        "Total lidas"]
       [:div {:style {:font-size (:lg t/font-sizes)
                      :font-weight (:semibold t/font-weights)}}
        (str (:total_lidas stats 0))]]
      [:div {:style {:padding "12px" :background t/bg-card
                     :border-radius (:md t/border-radius)
                     :border (str "1px solid " t/border-default)}}
       [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
        "Matched"]
       [:div {:style {:font-size (:lg t/font-sizes)
                      :font-weight (:semibold t/font-weights)
                      :color t/success-default}}
        (str (:matched result 0))]]
      [:div {:style {:padding "12px" :background t/bg-card
                     :border-radius (:md t/border-radius)
                     :border (str "1px solid " t/border-default)}}
       [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
        "Fora do período"]
       [:div {:style {:font-size (:lg t/font-sizes)}}
        (str (:descartadas_periodo stats 0))]]
      [:div {:style {:padding "12px" :background t/bg-card
                     :border-radius (:md t/border-radius)
                     :border (str "1px solid " t/border-default)}}
       [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
        "Missed"]
       [:div {:style {:font-size (:lg t/font-sizes)
                      :color t/error-default}}
        (str (:missed result 0))]]]

     (when (seq (:missed_clients result))
       [:div {:style {:padding "12px" :background "#FFF3CD"
                      :border-radius (:md t/border-radius)
                      :font-size (:sm t/font-sizes)}}
        [:strong "Clientes não encontrados: "]
        (clojure.string/join ", " (:missed_clients result))])

     [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
      [btn/button {:variant :secondary
                   :on-click #(rf/dispatch [:revops/perk-upload-reset])}
       "Novo Upload"]]]))

(defn financial-upload-page []
  (fn []
    (let [result       @(rf/subscribe [:revops/upload-result])
          loading?     @(rf/subscribe [:revops/upload-loading?])
          perk-result  @(rf/subscribe [:revops/perk-upload-result])
          perk-loading? @(rf/subscribe [:revops/perk-upload-loading?])
          user         @(rf/subscribe [:auth/current-user])
          route        @(rf/subscribe [:current-route-name])]
      [layout/page-shell
       {:sidebar-items revops-shell/sidebar-items
        :current-route route
        :user          user
        :title         "Upload Financeiro"
        :subtitle      "Importar dados financeiros e subsídios via XLSX"}

       [cards/card {}
        [:h3 {:style {:margin "0 0 16px 0" :font-size (:md t/font-sizes)}} "Faturamento"]
        (cond
          loading?
          [:div {:style {:padding "48px" :text-align "center"
                         :color t/text-secondary}}
           [:div {:style {:font-size "32px" :margin-bottom "12px"}} [:span {:aria-hidden "true"} "⚙️"]]
           "Processando arquivo..."]

          result
          [result-view result]

          :else
          [upload-form])]

       [:div {:style {:margin-top "24px"}}
        [cards/card {}
         [:h3 {:style {:margin "0 0 16px 0" :font-size (:md t/font-sizes)}} "Subsídios / Perks"]
         (cond
           perk-loading?
           [:div {:style {:padding "48px" :text-align "center"
                          :color t/text-secondary}}
            [:div {:style {:font-size "32px" :margin-bottom "12px"}} [:span {:aria-hidden "true"} "⚙️"]]
            "Processando subsídios..."]

           perk-result
           [perk-result-view perk-result]

           :else
           [perk-upload-form])]]])))
