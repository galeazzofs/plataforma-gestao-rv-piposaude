(ns app.views.revops.teams
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.buttons :as btn]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn empty-team-form [] {:name "" :leader_id ""})

(defn team-modal [{:keys [open? on-close team-data users]}]
  (let [form (r/atom (or team-data (empty-team-form)))]
    (fn []
      (let [editing? (some? (:id team-data))
            leader-options (into [{:value "" :label "Sem líder"}]
                                 (map #(hash-map :value (str (:id %)) :label (:name %))
                                      (filter #(= (:role %) "GERENTE") (or users []))))]
        [modal/modal {:open?    open?
                      :on-close on-close
                      :title    (if editing? "Editar Time" "Novo Time")
                      :size     :sm}
         [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
          [inputs/input
           {:label     "Nome do Time"
            :value     (:name @form)
            :required  true
            :on-change #(swap! form assoc :name %)}]
          [inputs/select
           {:label     "Líder (Gerente)"
            :value     (or (:leader_id @form) "")
            :options   leader-options
            :on-change #(swap! form assoc :leader_id %)}]
          [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
           [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
           [btn/button
            {:variant  :primary
             :disabled (clojure.string/blank? (:name @form))
             :on-click (fn []
                         (if editing?
                           (rf/dispatch [:revops/update-team (:id team-data) @form])
                           (rf/dispatch [:revops/create-team @form]))
                         (on-close))}
            (if editing? "Salvar" "Criar")]]]]))))

(defn teams-page []
  (rf/dispatch [:revops/fetch-teams])
  (rf/dispatch [:revops/fetch-users])
  (let [modal-open?  (r/atom false)
        editing-team (r/atom nil)
        team-columns [{:key :name        :label "Nome"       :sortable true}
                      {:key :leader_name :label "Líder"      :sortable false}
                      {:key :members     :label "Membros"    :sortable false :align "center" :width "80px"
                       :render (fn [row]
                                 [:span {:style {:display "inline-flex" :align-items "center" :justify-content "center"
                                                 :width "28px" :height "28px" :border-radius (:full t/border-radius)
                                                 :background t/beige-100 :color t/beige-700
                                                 :font-size (:xs t/font-sizes) :font-weight (:bold t/font-weights)}}
                                  (str (count (or (:members row) [])))])}
                      {:key :actions     :label ""           :sortable false :width "120px"
                       :render (fn [row]
                                 [:div {:style {:display "flex" :gap "6px"}}
                                  [btn/button {:variant :ghost :size :sm
                                               :on-click #(do (reset! editing-team row)
                                                              (reset! modal-open? true))}
                                   "Editar"]
                                  [btn/button {:variant :danger :size :sm
                                               :on-click #(when (js/confirm (str "Remover " (:name row) "?"))
                                                            (rf/dispatch [:revops/delete-team (:id row)]))}
                                   "Remover"]])}]]
    (fn []
      (let [teams    @(rf/subscribe [:revops/teams])
            users    @(rf/subscribe [:revops/users])
            loading? @(rf/subscribe [:revops/teams-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Times"
          :subtitle      "Gerenciar times e líderes"
          :header-actions
          [btn/button
           {:variant  :primary
            :on-click #(do (reset! editing-team nil)
                           (reset! modal-open? true))}
           "+ Novo Time"]}

         [cards/card {}
          [tbl/data-table
           {:columns       team-columns
            :rows          (or teams [])
            :empty-message (if loading? "Carregando..." "Nenhum time encontrado")}]]

         [team-modal {:open?     @modal-open?
                       :on-close  #(reset! modal-open? false)
                       :team-data @editing-team
                       :users     users}]]))))
